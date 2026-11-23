import './style.css';

// Official maintained web-component renderer.
import {A2uiSurface, basicCatalog} from '@a2ui/lit/v0_9';
import '@a2ui/lit/v0_9';
import {MessageProcessor, type SurfaceModel} from '@a2ui/web_core/v0_9';

const API = 'http://127.0.0.1:8080';
const sessionId = crypto.randomUUID();

const prompt = document.querySelector<HTMLTextAreaElement>('#prompt')!;
const ask = document.querySelector<HTMLButtonElement>('#ask')!;
const busy = document.querySelector<HTMLElement>('#busy')!;
const surfacesRoot = document.querySelector<HTMLElement>('#surfaces')!;
const empty = document.querySelector<HTMLElement>('#empty')!;
const count = document.querySelector<HTMLElement>('#surface-count')!;
const runtimeError = document.querySelector<HTMLElement>('#runtime-error')!;
const agentText = document.querySelector<HTMLElement>('#agent-text')!;
const validation = document.querySelector<HTMLElement>('#validation')!;
const confirmation = document.querySelector<HTMLElement>('#confirmation')!;
const wire = document.querySelector<HTMLElement>('#wire')!;

// The official processor owns protocol/state/data binding.
// The Lit renderer owns the actual Basic Catalog UI components.
const processor = new MessageProcessor([basicCatalog], (action: unknown) => {
  void handleAction(action as Record<string, any>);
});

const mounted = new Map<string, HTMLElement>();

processor.onSurfaceCreated((surface: SurfaceModel) => mountSurface(surface));
processor.onSurfaceDeleted((surfaceId: string) => {
  mounted.get(surfaceId)?.remove();
  mounted.delete(surfaceId);
  updateSurfaceCount();
});

function mountSurface(surface: SurfaceModel): void {
  let element = mounted.get(surface.id) as any;
  if (!element) {
    element = document.createElement('a2ui-surface') as A2uiSurface;
    element.surface = surface;
    surfacesRoot.appendChild(element);
    mounted.set(surface.id, element);
  } else {
    element.surface = surface;
  }
  updateSurfaceCount();
}

function updateSurfaceCount(): void {
  const n = mounted.size;
  count.textContent = `${n} surface${n === 1 ? '' : 's'}`;
  empty.hidden = n > 0;
}

function showError(message: string): void {
  runtimeError.hidden = false;
  runtimeError.innerHTML = `<strong>Runtime / transport error</strong><div>${escapeHtml(message)}</div>`;
}

function clearMessages(): void {
  runtimeError.hidden = true;
  validation.hidden = true;
  confirmation.hidden = true;
}

ask.addEventListener('click', async () => {
  clearMessages();
  ask.disabled = true;
  busy.hidden = false;
  try {
    const response = await fetch(`${API}/api/chat`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({session_id: sessionId, message: prompt.value}),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body?.detail ?? `HTTP ${response.status}`);

    for (const event of body.events ?? []) {
      if (event.kind === 'a2ui' && Array.isArray(event.messages) && event.messages.length) {
        wire.textContent = JSON.stringify(event.messages, null, 2);
        processor.processMessages(event.messages);
      }
      if (event.kind === 'text' && event.text) {
        agentText.hidden = false;
        agentText.innerHTML = `<div class="eyebrow">Agent text</div><p>${escapeHtml(event.text)}</p>`;
      }
    }
  } catch (error) {
    showError(error instanceof Error ? error.message : String(error));
  } finally {
    ask.disabled = false;
    busy.hidden = true;
  }
});

async function handleAction(action: Record<string, any>): Promise<void> {
  clearMessages();
  // A2UI resolves bound values into the action context before dispatch.
  const values = action?.context?.form ?? action?.context ?? {};

  try {
    const response = await fetch(`${API}/api/submit`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({session_id: sessionId, values}),
    });
    const body = await response.json();

    if (response.status === 422) {
      validation.hidden = false;
      const rows = Object.entries(body.field_errors ?? {}).map(([field, messages]) =>
        `<div class="field-error"><strong>${escapeHtml(field)}</strong>${escapeHtml((messages as string[]).join(' '))}</div>`
      ).join('');
      validation.innerHTML = `<h2>Please correct the form</h2><p>The backend returned a controlled 422 validation response.</p>${rows}`;
      return;
    }
    if (!response.ok) throw new Error(body?.detail ?? body?.message ?? `HTTP ${response.status}`);

    confirmation.hidden = false;
    confirmation.innerHTML = `<h2>Validated submission</h2><p>Nothing was stored. The backend printed and echoed this payload.</p><pre>${escapeHtml(JSON.stringify(body.submitted ?? {}, null, 2))}</pre>`;
  } catch (error) {
    showError(error instanceof Error ? error.message : String(error));
  }
}

function escapeHtml(value: unknown): string {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
