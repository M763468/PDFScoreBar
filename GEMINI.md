# Agent Policy for this repo

## Bootstrap on the first turn of each new session
Perform these steps **before** answering feature/bug requests:

0) **Start Docker Container**
   - Ensure the `pdf_score_dev_gpu` container is running.
   - Run the following command:
     ```bash
     docker start pdf_score_dev_gpu
     ```

## Execution style
- Explain what you’re about to do, then execute.
- After edits, run tests/linters; summarize diffs and failures.

## End-of-Session Documentation Rule

At the end of each session, I will update the project's Markdown files to reflect the progress made. I will ask for your confirmation before making these updates.

-   **`DEVELOPMENT_LOG.md`**: A log of the key activities, decisions, and outcomes from the session.
-   **`NEXT_SESSION_NOTES.md`**: Planned next steps, open questions, or new ideas.
-   **`README.md`**: Updates to the project's overall description, setup, or usage, if any.

# Project Context Links

To understand the project, I will refer to the following source-of-truth documents. I will keep these updated based on our work.

-   **Project Overview, Usage, and Core Technology:**
    -   See: `README.md`

-   **Development History and Key Decisions:**
    -   See: `DEVELOPMENT_LOG.md`

-   **Current Tasks and Future Plans:**
    -   See: `NEXT_SESSION_NOTES.md`
