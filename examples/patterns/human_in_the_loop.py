"""Pattern: Human-in-the-Loop (HITL).

A WorkflowAgent pauses at a critical step and waits for human approval
before proceeding. Approval is modelled as a second message to the same
agent — no special framework support needed.

The pattern:
  1. Agent receives a task and processes it to a decision point
  2. Agent stores pending state and replies with a "needs_approval" signal
  3. Human (or test harness) sends an "approve" or "reject" message
  4. Agent resumes or aborts based on the decision

Use this when:
  - An action is irreversible (deploy, send email, charge card)
  - Regulatory requirements mandate human sign-off
  - Confidence is below a threshold

Run:
    uv run python examples/patterns/human_in_the_loop.py
"""

import asyncio

from civitas import AgentProcess, Runtime, Supervisor
from civitas.messages import Message


class WorkflowAgent(AgentProcess):
    """Processes a deployment request, pauses for approval, then executes."""

    async def on_start(self) -> None:
        # pending holds tasks awaiting human approval
        self.state.setdefault("pending", {})
        self.state.setdefault("completed", [])

    async def handle(self, message: Message) -> Message | None:
        msg_type = message.payload.get("type", "task")

        if msg_type == "task":
            return await self._handle_task(message)
        elif msg_type == "approval":
            return await self._handle_approval(message)
        else:
            return self.reply({"error": f"unknown message type: {msg_type}"})

    async def _handle_task(self, message: Message) -> Message | None:
        task_id = message.payload.get("task_id", "unknown")
        action = message.payload.get("action", "")
        risk = message.payload.get("risk", "low")

        print(f"  [workflow] Received task {task_id}: {action!r} (risk={risk})")

        if risk in ("high", "critical"):
            # Store the pending task and ask for approval
            self.state["pending"][task_id] = message.payload
            print(f"  [workflow] High-risk action — pausing for human approval")
            return self.reply({
                "status": "needs_approval",
                "task_id": task_id,
                "action": action,
                "risk": risk,
                "message": f"Task {task_id} requires approval before executing.",
            })

        # Low-risk: execute immediately
        result = self._execute(task_id, action)
        self.state["completed"].append(task_id)
        return self.reply({"status": "done", "task_id": task_id, "result": result})

    async def _handle_approval(self, message: Message) -> Message | None:
        task_id = message.payload.get("task_id", "")
        decision = message.payload.get("decision", "reject")  # "approve" or "reject"
        approver = message.payload.get("approver", "unknown")

        pending = self.state["pending"].pop(task_id, None)
        if pending is None:
            return self.reply({"error": f"no pending task with id={task_id!r}"})

        if decision == "approve":
            print(f"  [workflow] Approved by {approver} — executing {task_id}")
            result = self._execute(task_id, pending["action"])
            self.state["completed"].append(task_id)
            return self.reply({
                "status": "done",
                "task_id": task_id,
                "approver": approver,
                "result": result,
            })
        else:
            print(f"  [workflow] Rejected by {approver} — aborting {task_id}")
            return self.reply({
                "status": "rejected",
                "task_id": task_id,
                "approver": approver,
            })

    def _execute(self, task_id: str, action: str) -> str:
        return f"Executed '{action}' for task {task_id}"


async def main() -> None:
    runtime = Runtime(
        supervisor=Supervisor("root", children=[WorkflowAgent("workflow")])
    )
    await runtime.start()

    # --- Task 1: low-risk, executes immediately ---
    print("Task 1: low-risk deploy to staging")
    r1 = await runtime.ask("workflow", {
        "type": "task",
        "task_id": "t001",
        "action": "deploy staging-v1.2",
        "risk": "low",
    })
    print(f"  → status={r1.payload['status']}\n")

    # --- Task 2: high-risk, pauses for approval ---
    print("Task 2: high-risk deploy to production")
    r2 = await runtime.ask("workflow", {
        "type": "task",
        "task_id": "t002",
        "action": "deploy production-v1.2",
        "risk": "high",
    })
    print(f"  → status={r2.payload['status']}: {r2.payload['message']}\n")

    # Simulate human reviewing and approving
    await asyncio.sleep(0.1)
    print("Human reviews and approves t002...")
    r3 = await runtime.ask("workflow", {
        "type": "approval",
        "task_id": "t002",
        "decision": "approve",
        "approver": "alice@example.com",
    })
    print(f"  → status={r3.payload['status']}, result={r3.payload['result']!r}\n")

    # --- Task 3: high-risk, rejected ---
    print("Task 3: critical action, rejected by human")
    r4 = await runtime.ask("workflow", {
        "type": "task",
        "task_id": "t003",
        "action": "drop production database",
        "risk": "critical",
    })
    r5 = await runtime.ask("workflow", {
        "type": "approval",
        "task_id": "t003",
        "decision": "reject",
        "approver": "bob@example.com",
    })
    print(f"  → status={r5.payload['status']}\n")

    # Summary
    agent = runtime.get_agent("workflow")
    print(f"Completed tasks: {agent.state['completed']}")
    print(f"Pending tasks:   {list(agent.state['pending'].keys())}")

    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
