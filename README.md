# CourseDigest

Digests a DeepLearning.AI course into a short visual site: plain-English lesson cards, worked examples, diagrams, the video moments worth watching, and the ungraded labs run end to end with a walkthrough.

## Setup (Windows, Python 3.11)

```bash
py -3.11 -m venv .venv
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\playwright install chromium
copy .env.example .env   # then fill in GEMINI_API_KEY (free: aistudio.google.com) and TAVILY_API_KEY
```

## Use

```bash
coursedigest login                                                    # once, from your own terminal: sign in, close the window
coursedigest all https://learn.deeplearning.ai/courses/agentic-ai     # fetch + digest + labs + site
```

Or step by step: `fetch <course-url>`, `digest <course>`, `labs <course>`, `site <course>`. The site lands in `site/<course>/index.html`.
