from a2ui.adk import A2uiProcessorStore, SendA2uiToClientToolset
from a2ui.core.basic_catalog import BasicCatalog
from a2ui.processor import A2uiRequestProcessor

PROCESSORS = A2uiProcessorStore()

PROCESSOR = A2uiRequestProcessor([BasicCatalog("v0.9")])

A2UI_TOOLSET = SendA2uiToClientToolset(
    a2ui_enabled = PROCESSORS.is_enabled,
    a2ui_processor = PROCESSORS.get,

)

def enable_a2ui(session_id: str) -> None:
    """Register the processor for this session. Without this, A2UI stays
    disabled: no tool is exposed and no A2UI prompt is added."""
    PROCESSORS.set(session_id, PROCESSOR)
