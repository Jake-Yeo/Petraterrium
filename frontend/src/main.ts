import './styles.css';
import { SimulationWorkspace } from './simulation/workspace';
import { shell } from './views';

const app = document.getElementById('app');
if (!app) throw new Error('Missing application root');
app.innerHTML = shell();

const workspace = new SimulationWorkspace({
  onSectionChange: () => {},
  onError: (error) => {
    const status = document.getElementById('api-status');
    if (status) {
      status.textContent = error instanceof Error ? error.message : String(error);
      status.classList.remove('connected');
    }
  },
});

const status = document.getElementById('api-status');
fetch('/api/health')
  .then((response) => {
    if (!response.ok) throw new Error(`API health failed (${response.status})`);
    if (status) {
      status.textContent = 'Rust DSL connected';
      status.classList.add('connected');
    }
  })
  .catch((error: unknown) => {
    if (status) {
      status.textContent = error instanceof Error ? error.message : String(error);
      status.classList.remove('connected');
    }
  });

window.addEventListener('pagehide', () => workspace.destroy(), { once: true });
