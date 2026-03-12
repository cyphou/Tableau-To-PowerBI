# Agent Behavior Instructions

General rules for AI coding agents working in this codebase. These apply to all tasks regardless of scope.

---

## Workflow Modes

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity
- Plan output goes to `tasks/todo.md` OR your native task tracker (whichever is available)

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution
- If subagents are unavailable, batch all research before implementation

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project
- NOTE: The user will inject `tasks/lessons.md` into context at session start. If it's not in context, ask for it before starting work.

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes — summarize what changed and why
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness
- Include test command + pass/fail count in your completion summary

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

### 7. Scope Discipline
- Only modify files directly related to the task
- No drive-by refactors, no "while I'm here" improvements
- If you spot an unrelated issue, note it in your summary — don't fix it
- Ask before adding new dependencies
- Prefer the smallest change that solves the problem

### 8. Testing Contract
- Run the full test suite after every implementation change
- If tests fail, fix them before reporting completion
- Always include test command + pass/fail count in your summary
- New features require new tests — no exceptions
- Never weaken test assertions to make tests pass if the code is wrong

### 9. Git Hygiene
- Commit with conventional-style messages (feat/fix/refactor/docs)
- Never commit generated artifacts, caches, or temp files
- Stage only files related to the current task
- Push only when tests pass

---

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` or your native task tracker with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

---

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Blast Radius**: Touch fewer files > touch more files. Edit fewer lines > edit more lines.
- **Read Before Write**: Always read the target code before editing it. Never assume file contents from memory or context summaries.
- **Fail Loudly**: If you can't complete a task, say so clearly with the reason. Never silently skip a step or produce partial output without flagging it.
- **Own the Outcome**: You are responsible for the correctness of your output. Don't shift verification to the user.

---

## Anti-Patterns (Never Do These)

- Don't apologize or ask permission — just execute
- Don't explain what you're "about to do" — do it, then summarize
- Don't create summary/documentation files unless asked
- Don't modify test assertions to make tests pass if the code is wrong
- Don't use placeholder values like "TODO" or "FIXME" in shipped code
- Don't re-read files you've already read in this session unless they changed
- Don't ask "should I continue?" — always continue until done
- Don't touch files outside the task scope
- Don't add dependencies without asking
