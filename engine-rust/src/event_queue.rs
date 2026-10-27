use crate::agent_types::ActionEvent;
use std::collections::VecDeque;

#[derive(Default)]
pub struct EventQueue {
    pending: VecDeque<ActionEvent>,
}

impl EventQueue {
    pub fn push(&mut self, event: ActionEvent) {
        self.pending.push_back(event);
    }

    pub fn drain(&mut self) -> Vec<ActionEvent> {
        self.pending.drain(..).collect()
    }
}
