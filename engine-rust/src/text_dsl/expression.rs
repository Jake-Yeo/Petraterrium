use super::model::{DslError, DslResult, DslValue, Expr};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, PartialEq)]
enum Token {
    Number(f64),
    Identifier(String),
    Operator(String),
    LeftParen,
    RightParen,
    Comma,
}

pub fn parse_expression(source: &str, line: usize) -> DslResult<Expr> {
    let tokens = tokenize(source, line)?;
    let mut parser = ExpressionParser {
        tokens,
        position: 0,
        line,
    };
    let expression = parser.conditional()?;
    if parser.position != parser.tokens.len() {
        return Err(DslError::new(
            "INVALID_EXPRESSION",
            line,
            format!("Unexpected token in expression {source:?}"),
        ));
    }
    Ok(expression)
}

fn tokenize(source: &str, line: usize) -> DslResult<Vec<Token>> {
    let characters = source.chars().collect::<Vec<_>>();
    let mut tokens = Vec::new();
    let mut index = 0;
    while index < characters.len() {
        let character = characters[index];
        if character.is_whitespace() {
            index += 1;
            continue;
        }
        if character.is_ascii_digit()
            || (character == '.'
                && characters
                    .get(index + 1)
                    .is_some_and(|value| value.is_ascii_digit()))
        {
            let start = index;
            index += 1;
            while index < characters.len()
                && (characters[index].is_ascii_digit()
                    || characters[index] == '.'
                    || matches!(characters[index], 'e' | 'E' | '+' | '-')
                        && matches!(characters[index - 1], 'e' | 'E'))
            {
                index += 1;
            }
            let value = source[start..index].parse::<f64>().map_err(|_| {
                DslError::new(
                    "INVALID_NUMBER",
                    line,
                    format!("Invalid number {}", &source[start..index]),
                )
            })?;
            tokens.push(Token::Number(value));
            continue;
        }
        if character.is_ascii_alphabetic() || character == '_' {
            let start = index;
            index += 1;
            while index < characters.len()
                && (characters[index].is_ascii_alphanumeric()
                    || matches!(characters[index], '_' | '.'))
            {
                index += 1;
            }
            tokens.push(Token::Identifier(source[start..index].to_owned()));
            continue;
        }
        if character == '(' {
            tokens.push(Token::LeftParen);
            index += 1;
            continue;
        }
        if character == ')' {
            tokens.push(Token::RightParen);
            index += 1;
            continue;
        }
        if character == ',' {
            tokens.push(Token::Comma);
            index += 1;
            continue;
        }
        let double = characters
            .get(index + 1)
            .map(|next| format!("{character}{next}"));
        if double
            .as_deref()
            .is_some_and(|value| matches!(value, "==" | "!=" | ">=" | "<="))
        {
            tokens.push(Token::Operator(double.unwrap()));
            index += 2;
            continue;
        }
        if matches!(character, '+' | '-' | '*' | '/' | '>' | '<') {
            tokens.push(Token::Operator(character.to_string()));
            index += 1;
            continue;
        }
        return Err(DslError::new(
            "INVALID_EXPRESSION",
            line,
            format!("Unsupported character {character:?} in expression"),
        ));
    }
    Ok(tokens)
}

struct ExpressionParser {
    tokens: Vec<Token>,
    position: usize,
    line: usize,
}

impl ExpressionParser {
    fn conditional(&mut self) -> DslResult<Expr> {
        let when_true = self.logical_or()?;
        if self.consume_identifier("if") {
            let condition = self.logical_or()?;
            if !self.consume_identifier("else") {
                return Err(DslError::new(
                    "INVALID_EXPRESSION",
                    self.line,
                    "Conditional expressions require else",
                ));
            }
            let when_false = self.conditional()?;
            return Ok(Expr::Conditional {
                condition: Box::new(condition),
                when_true: Box::new(when_true),
                when_false: Box::new(when_false),
            });
        }
        Ok(when_true)
    }

    fn logical_or(&mut self) -> DslResult<Expr> {
        let mut expression = self.logical_and()?;
        while self.consume_identifier("or") {
            expression = Expr::Binary {
                operation: "or".to_owned(),
                left: Box::new(expression),
                right: Box::new(self.logical_and()?),
            };
        }
        Ok(expression)
    }

    fn logical_and(&mut self) -> DslResult<Expr> {
        let mut expression = self.comparison()?;
        while self.consume_identifier("and") {
            expression = Expr::Binary {
                operation: "and".to_owned(),
                left: Box::new(expression),
                right: Box::new(self.comparison()?),
            };
        }
        Ok(expression)
    }

    fn comparison(&mut self) -> DslResult<Expr> {
        let mut expression = self.additive()?;
        while let Some(operation) = self.consume_operator(&["==", "!=", ">=", "<=", ">", "<"]) {
            expression = Expr::Binary {
                operation,
                left: Box::new(expression),
                right: Box::new(self.additive()?),
            };
        }
        Ok(expression)
    }

    fn additive(&mut self) -> DslResult<Expr> {
        let mut expression = self.multiplicative()?;
        while let Some(operation) = self.consume_operator(&["+", "-"]) {
            expression = Expr::Binary {
                operation,
                left: Box::new(expression),
                right: Box::new(self.multiplicative()?),
            };
        }
        Ok(expression)
    }

    fn multiplicative(&mut self) -> DslResult<Expr> {
        let mut expression = self.unary()?;
        while let Some(operation) = self.consume_operator(&["*", "/"]) {
            expression = Expr::Binary {
                operation,
                left: Box::new(expression),
                right: Box::new(self.unary()?),
            };
        }
        Ok(expression)
    }

    fn unary(&mut self) -> DslResult<Expr> {
        if let Some(operation) = self.consume_operator(&["+", "-"]) {
            return Ok(Expr::Unary {
                operation,
                value: Box::new(self.unary()?),
            });
        }
        if self.consume_identifier("not") {
            return Ok(Expr::Unary {
                operation: "not".to_owned(),
                value: Box::new(self.unary()?),
            });
        }
        self.primary()
    }

    fn primary(&mut self) -> DslResult<Expr> {
        let token = self.tokens.get(self.position).cloned().ok_or_else(|| {
            DslError::new(
                "INVALID_EXPRESSION",
                self.line,
                "Expression ended unexpectedly",
            )
        })?;
        self.position += 1;
        match token {
            Token::Number(value) => Ok(Expr::Value(DslValue::Number(value))),
            Token::Identifier(value) if value == "true" => Ok(Expr::Value(DslValue::Bool(true))),
            Token::Identifier(value) if value == "false" => Ok(Expr::Value(DslValue::Bool(false))),
            Token::Identifier(value) if self.consume_token(&Token::LeftParen) => {
                let mut arguments = Vec::new();
                if !self.consume_token(&Token::RightParen) {
                    loop {
                        arguments.push(self.conditional()?);
                        if self.consume_token(&Token::RightParen) {
                            break;
                        }
                        if !self.consume_token(&Token::Comma) {
                            return Err(DslError::new(
                                "INVALID_EXPRESSION",
                                self.line,
                                "Function arguments require commas",
                            ));
                        }
                    }
                }
                Ok(Expr::Call {
                    function: value,
                    arguments,
                })
            }
            Token::Identifier(value) => Ok(Expr::Variable(value)),
            Token::LeftParen => {
                let value = self.conditional()?;
                if !self.consume_token(&Token::RightParen) {
                    return Err(DslError::new(
                        "INVALID_EXPRESSION",
                        self.line,
                        "Expression is missing a closing parenthesis",
                    ));
                }
                Ok(value)
            }
            _ => Err(DslError::new(
                "INVALID_EXPRESSION",
                self.line,
                "Expected a number, variable, or parenthesized expression",
            )),
        }
    }

    fn consume_identifier(&mut self, expected: &str) -> bool {
        if self.tokens.get(self.position) == Some(&Token::Identifier(expected.to_owned())) {
            self.position += 1;
            return true;
        }
        false
    }

    fn consume_operator(&mut self, expected: &[&str]) -> Option<String> {
        let Token::Operator(value) = self.tokens.get(self.position)? else {
            return None;
        };
        if expected.contains(&value.as_str()) {
            self.position += 1;
            return Some(value.clone());
        }
        None
    }

    fn consume_token(&mut self, expected: &Token) -> bool {
        if self.tokens.get(self.position) == Some(expected) {
            self.position += 1;
            return true;
        }
        false
    }
}

pub trait ValueResolver {
    fn resolve(&self, name: &str) -> Option<DslValue>;
}

impl ValueResolver for BTreeMap<String, DslValue> {
    fn resolve(&self, name: &str) -> Option<DslValue> {
        self.get(name).cloned()
    }
}

pub fn evaluate(expression: &Expr, values: &(impl ValueResolver + ?Sized)) -> DslResult<DslValue> {
    match expression {
        Expr::Value(value) => Ok(value.clone()),
        Expr::Variable(name) => values
            .resolve(name)
            .or_else(|| name.starts_with("role.").then(|| DslValue::Bool(false)))
            .or_else(|| {
                name.chars()
                    .next()
                    .is_some_and(char::is_uppercase)
                    .then(|| DslValue::Text(name.clone()))
            })
            .ok_or_else(|| DslError::new("UNKNOWN_VALUE", 1, format!("Unknown value {name}"))),
        Expr::Unary { operation, value } => {
            let value = evaluate(value, values)?;
            match operation.as_str() {
                "+" => Ok(DslValue::Number(number(&value)?)),
                "-" => Ok(DslValue::Number(-number(&value)?)),
                "not" => Ok(DslValue::Bool(!boolean(&value)?)),
                _ => Err(DslError::new(
                    "INVALID_EXPRESSION",
                    1,
                    "Unknown unary operation",
                )),
            }
        }
        Expr::Binary {
            operation,
            left,
            right,
        } => {
            let left = evaluate(left, values)?;
            if operation == "and" && !boolean(&left)? {
                return Ok(DslValue::Bool(false));
            }
            if operation == "or" && boolean(&left)? {
                return Ok(DslValue::Bool(true));
            }
            let right = evaluate(right, values)?;
            match operation.as_str() {
                "+" => Ok(DslValue::Number(number(&left)? + number(&right)?)),
                "-" => Ok(DslValue::Number(number(&left)? - number(&right)?)),
                "*" => Ok(DslValue::Number(number(&left)? * number(&right)?)),
                "/" => Ok(DslValue::Number(number(&left)? / number(&right)?)),
                "and" => Ok(DslValue::Bool(boolean(&left)? && boolean(&right)?)),
                "or" => Ok(DslValue::Bool(boolean(&left)? || boolean(&right)?)),
                "==" => Ok(DslValue::Bool(equal(&left, &right))),
                "!=" => Ok(DslValue::Bool(!equal(&left, &right))),
                ">" => Ok(DslValue::Bool(number(&left)? > number(&right)?)),
                ">=" => Ok(DslValue::Bool(number(&left)? >= number(&right)?)),
                "<" => Ok(DslValue::Bool(number(&left)? < number(&right)?)),
                "<=" => Ok(DslValue::Bool(number(&left)? <= number(&right)?)),
                _ => Err(DslError::new(
                    "INVALID_EXPRESSION",
                    1,
                    "Unknown binary operation",
                )),
            }
        }
        Expr::Conditional {
            condition,
            when_true,
            when_false,
        } => {
            if boolean(&evaluate(condition, values)?)? {
                evaluate(when_true, values)
            } else {
                evaluate(when_false, values)
            }
        }
        Expr::Call {
            function,
            arguments,
        } => {
            let arguments = arguments
                .iter()
                .map(|argument| evaluate(argument, values).and_then(|value| number(&value)))
                .collect::<DslResult<Vec<_>>>()?;
            let value = match (function.as_str(), arguments.as_slice()) {
                ("min", [left, right]) => left.min(*right),
                ("max", [left, right]) => left.max(*right),
                ("clamp", [value, minimum, maximum]) => value.clamp(*minimum, *maximum),
                _ => {
                    return Err(DslError::new(
                        "INVALID_EXPRESSION",
                        1,
                        format!("Unsupported function {function}"),
                    ));
                }
            };
            Ok(DslValue::Number(value))
        }
    }
}

pub fn references(expression: &Expr) -> BTreeSet<String> {
    let mut result = BTreeSet::new();
    collect_references(expression, &mut result);
    result
}

fn collect_references(expression: &Expr, result: &mut BTreeSet<String>) {
    match expression {
        Expr::Variable(value) => {
            if value
                .chars()
                .next()
                .is_some_and(|character| character.is_lowercase())
                || value.contains('_')
                || value.contains('.')
            {
                result.insert(value.clone());
            }
        }
        Expr::Unary { value, .. } => collect_references(value, result),
        Expr::Binary { left, right, .. } => {
            collect_references(left, result);
            collect_references(right, result);
        }
        Expr::Conditional {
            condition,
            when_true,
            when_false,
        } => {
            collect_references(condition, result);
            collect_references(when_true, result);
            collect_references(when_false, result);
        }
        Expr::Call { arguments, .. } => {
            for argument in arguments {
                collect_references(argument, result);
            }
        }
        Expr::Value(_) => {}
    }
}

fn number(value: &DslValue) -> DslResult<f64> {
    value
        .as_f64()
        .ok_or_else(|| DslError::new("TYPE_ERROR", 1, "Expected a numeric value"))
}

fn boolean(value: &DslValue) -> DslResult<bool> {
    value
        .as_bool()
        .ok_or_else(|| DslError::new("TYPE_ERROR", 1, "Expected a boolean value"))
}

fn equal(left: &DslValue, right: &DslValue) -> bool {
    match (left, right) {
        (DslValue::Number(left), DslValue::Number(right)) => (left - right).abs() <= 1e-12,
        (DslValue::Bool(left), DslValue::Bool(right)) => left == right,
        (DslValue::Text(left), DslValue::Text(right)) => left == right,
        _ => false,
    }
}
