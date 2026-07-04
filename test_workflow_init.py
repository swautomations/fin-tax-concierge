from google.adk.workflow import Workflow, START, FunctionNode
from google.adk.agents import LlmAgent
from google.adk.apps import App
from pydantic import BaseModel

def security_checkpoint(ctx, node_input):
    return "test"

def security_handler(node_input):
    return "test"

def compliance_approval_gate(ctx, node_input):
    return "test"

def final_output(ctx, node_input):
    return "test"

orchestrator = LlmAgent(
    name="orchestrator",
    model="gemini-2.5-flash",
    instruction="test"
)

security_checkpoint_node = FunctionNode(func=security_checkpoint, name="security_checkpoint")
security_handler_node = FunctionNode(func=security_handler, name="security_handler")
compliance_approval_gate_node = FunctionNode(func=compliance_approval_gate, name="compliance_approval_gate")
final_output_node = FunctionNode(func=final_output, name="final_output")

# Test 1: Using dict routing format
try:
    edges = [
        (START, security_checkpoint_node),
        (security_checkpoint_node, {"SECURITY_EVENT": security_handler_node, "SECURE": orchestrator}),
        (orchestrator, compliance_approval_gate_node),
        (compliance_approval_gate_node, final_output_node),
        (security_handler_node, final_output_node),
    ]
    wf = Workflow(name="test_wf", edges=edges)
    print("Test 1 (Dict syntax) succeeded!")
except Exception as e:
    print("Test 1 (Dict syntax) failed:", e)

# Test 2: Using Edge objects
try:
    from google.adk.workflow import Edge
    # Need to see if we can construct Edges
    # Note: Edge expects BaseNode instances. Let's see if Workflow wraps LlmAgent beforehand.
    # In Workflow code, does it auto-wrap?
    edges2 = [
        Edge(from_node=START, to_node=security_checkpoint_node),
        # Since orchestrator is LlmAgent, can we pass it or do we wrap it?
        # Let's see if Edge accepts it or if Workflow has a wrapper.
    ]
    print("Edge import and simple construction succeeded!")
except Exception as e:
    print("Edge construction failed:", e)
