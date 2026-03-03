# Agent From Scratch Contributions

This repo accepts community submissions for:

- Snippet improvements
- Code golf records
- Challenge claims
- Polis submissions (full agent transcript package)

## Quick Links

- `Send a PR`: [https://github.com/brotchie/agent-from-scratch#how-to-submit-a-pull-request](https://github.com/brotchie/agent-from-scratch#how-to-submit-a-pull-request)
- `Submit your score`: [https://github.com/brotchie/agent-from-scratch#submit-your-score-code-golf](https://github.com/brotchie/agent-from-scratch#submit-your-score-code-golf)
- `Claim`: [https://github.com/brotchie/agent-from-scratch#claim-a-challenge](https://github.com/brotchie/agent-from-scratch#claim-a-challenge)
- `Submit to the Polis`: [https://github.com/brotchie/agent-from-scratch#submit-to-the-polis](https://github.com/brotchie/agent-from-scratch#submit-to-the-polis)
- `Be the first`: [https://github.com/brotchie/agent-from-scratch#submit-to-the-polis](https://github.com/brotchie/agent-from-scratch#submit-to-the-polis)
- `File an issue`: [https://github.com/brotchie/agent-from-scratch/issues/new?title=Snippet+not+working&labels=bug](https://github.com/brotchie/agent-from-scratch/issues/new?title=Snippet+not+working&labels=bug)

## How To Submit A Pull Request

1. Fork this repository.
2. Create a branch from `main` in your fork.
3. Make your changes.
4. Commit with a clear message.
5. Push the branch to your fork.
6. Open a Pull Request to `brotchie/agent-from-scratch:main`.
7. In the PR body, include what you changed, why you changed it, and any proof/screenshots/logs needed to verify it.

## Submit Your Score (Code Golf)

Open a PR that directly updates the website to show you as the new code golf winner (for the relevant model/challenge card), then include evidence in the PR description.

Your PR should include:

- Model name
- Final snippet
- Byte count
- Proof the snippet bootstraps a working REPL
- The website change that updates the displayed winner/record
- Any constraints or caveats

## Claim A Challenge

Open a PR that directly updates the website to show you as the challenge winner, then include evidence in the PR description.

Your PR must include:

- Challenge name
- Evidence it was completed
- Steps to reproduce
- Relevant logs/screenshots/links
- The website change that updates the challenge status/winner
- Your Twitter handle shown in the website challenge update
- A Polis submission: either a new one in this PR or a link to an existing one in the repo

## Submit To The Polis

Put your submission in:

- `polis/<agentname>/afs.json`
- `polis/<agentname>/images/` for screenshots or other media

### Polis JSON Format

Use this top-level JSON object:

- `submitter`: object with identity details
- `agent_name`: string
- `genesis_snippet`: string
- `model_response`: string containing the raw model response used to extract/build the generated agent REPL
- `turns`: array of turn objects in chronological order, each with:
  - `type`: `"user"` or `"agent"`
  - `content`: markdown string
- `agent_description_md`: markdown string (can reference images in `images/`)

Recommended submitter fields:

- `name`: string
- `twitter_handle`: string, like `@yourhandle`
- `github_username`: string

### Example `afs.json`

```json
{
  "submitter": {
    "name": "Jane Doe",
    "twitter_handle": "@janedoe",
    "github_username": "janedoe"
  },
  "agent_name": "helios",
  "genesis_snippet": "read -p \"Gemini API key: \" k && ... && ./afs.py",
  "model_response": "{ \"candidates\": [ { \"content\": { \"parts\": [ { \"text\": \"#!/usr/bin/env python3\\n...generated agent REPL...\" } ] } } ] }",
  "turns": [
    {
      "type": "user",
      "content": "Rewrite yourself to support disk-backed history."
    },
    {
      "type": "agent",
      "content": "Implemented history persistence in `~/.afs_history` and added load/save behavior."
    },
    {
      "type": "user",
      "content": "Add a /restart command and preserve conversation state."
    },
    {
      "type": "agent",
      "content": "Added `/restart` that checkpoints conversation to disk and rehydrates on boot."
    },
    {
      "type": "user",
      "content": "Integrate Telegram long polling."
    }
  ],
  "agent_description_md": "# Helios\n\nHelios is a self-rewriting CLI agent focused on reliability and low token usage.\n\n## Highlights\n\n- Self-upgrading REPL\n- Tool output summarization\n- Telegram interface\n\n## Screenshots\n\n![Terminal run](images/terminal-run.png)\n![Telegram chat](images/telegram-chat.png)"
}
```

## Submission Checklist

- Secrets redacted (`[REDACTED]`)
- Reproducible proof included
- Files placed in the expected path
- PR description is clear and complete
- Polis submissions include both `genesis_snippet` and `model_response`
- Polis submissions include `turns` with both user and agent messages where possible
- Code golf/challenge PRs directly modify the site to reflect your claimed win
- Challenge site updates include the submitter's Twitter handle
- Challenge PRs include a new or existing Polis submission
- Claims with external dependencies (for example tweets, demos, or third-party posts) include supporting evidence links/screenshots
