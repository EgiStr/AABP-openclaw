---
name: notebooklm-research
description: "Autonomous research skill using NotebookLM MCP to ingest technical documents, GitHub repos, and URLs — then extract insights, generate slides, infographics, and visual content for LinkedIn posts."
---

# NotebookLM Research & Studio Skill

## When to Use
Invoke this skill whenever the user:
- Provides a **GitHub repo URL**, **technical article**, or **long-form document**
- Requests deep research: "baca repo ini", "research this", "analisis dokumen ini"
- Asks for **visual content**: "buatkan slide", "buat infografis", "buat thumbnail"
- Needs **supporting materials** for a LinkedIn post (slide carousel, infographic summary)

## Prerequisites
- **NotebookLM MCP server** installed and authenticated:
  ```bash
  uv tool install notebooklm-mcp-server
  notebooklm-mcp-auth
  ```
- The MCP server must be connected in `openclaw.json` (already configured).

---

## Part 1: Research Workflow

### Step 1: Acknowledge the User
> "Baik, saya sedang membaca [source description] via NotebookLM... ⏳"

### Step 2: Create a Research Notebook
```
Tool: notebook_create
Args: { "title": "[Project Name] - Research" }
```
Save the returned `notebook_id` for all subsequent calls.

### Step 3: Ingest Sources
For each URL/source provided by the user:
```
Tool: notebook_add_url
Args: { "notebook_id": "<id>", "url": "<source_url>" }
```

**Supported source types:**
- GitHub repository URLs (README + linked docs)
- Web articles and documentation pages
- YouTube video URLs
- Google Drive documents (Docs, Slides, Sheets)

For raw text or code snippets:
```
Tool: notebook_add_text
Args: { "notebook_id": "<id>", "text": "<content>" }
```

### Step 4: Run Research Analysis
```
Tool: research_start
Args: { "notebook_id": "<id>" }
```

### Step 5: Poll for Completion
```
Tool: research_status
Args: { "notebook_id": "<id>" }
```
Poll every 5-10 seconds until status is `completed`.

### Step 6: Import Insights
```
Tool: research_import
Args: { "notebook_id": "<id>" }
```

### Step 7: Extract Key Points
From the imported research, extract:
1. **Problem Statement**: What problem does this project solve?
2. **Technical Architecture**: Key components, data flow, tech stack choices
3. **Unique Selling Points**: What makes this approach interesting or novel?
4. **Lessons Learned**: Design trade-offs, challenges overcome
5. **Impact/Results**: Metrics, performance gains, user feedback

These become raw material for the Drafting Phase in AGENTS.md.

---

## Part 2: Studio Artifact Generation

Use NotebookLM's studio tools to create visual assets **after research is complete**. Always have a populated notebook with ingested sources before generating studio artifacts.

### Slide Deck Generation

**When to use**: User asks for presentation slides, carousel content, or visual breakdown of a technical topic.

**Best Practices:**
- Run research first — slides are generated FROM the notebook's ingested sources
- Configure chat context before creating slides to guide tone and depth
- Great for: LinkedIn carousel posts, tech talks, portfolio showcases

**Workflow:**
```
# 1. Configure the notebook's output style
Tool: chat_configure
Args: {
  "notebook_id": "<id>",
  "goal": "Create a technical presentation for LinkedIn audience",
  "response_length": "detailed"
}

# 2. Generate slide deck
Tool: slide_deck_create
Args: { "notebook_id": "<id>" }

# 3. Poll for completion
Tool: studio_status
Args: { "notebook_id": "<id>" }
# Repeat until status is "completed" (may take 1-3 minutes)
```

**Output**: Returns a link to the generated slide deck. Share with the user for review.

### Infographic Generation

**When to use**: User needs a visual summary, architecture diagram, comparison chart, or thumbnail-quality image for a LinkedIn post.

**Best Practices:**
- Infographics work best when the notebook has **focused, structured content** (not raw code dumps)
- Before generating, use `chat_configure` to set a clear visual goal
- Ideal for: LinkedIn cover images, architecture overviews, "key takeaways" visuals, post thumbnails

**Workflow:**
```
# 1. Configure for visual output
Tool: chat_configure
Args: {
  "notebook_id": "<id>",
  "goal": "Create a clear visual infographic summarizing the key technical concepts and architecture",
  "response_length": "concise"
}

# 2. Generate infographic
Tool: infographic_create
Args: { "notebook_id": "<id>" }

# 3. Poll for completion
Tool: studio_status
Args: { "notebook_id": "<id>" }
```

**Output**: Returns a link to the generated infographic. Can be used as:
- LinkedIn post thumbnail/cover image
- Visual summary in a carousel
- Supporting material in a technical article

---

## Part 3: Thumbnail & Visual Content Strategy

### Generating Post Thumbnails

For LinkedIn posts that need an eye-catching thumbnail:

**Option A — NotebookLM Infographic (Recommended for technical content)**
1. Ensure the research notebook has ingested relevant sources
2. Configure chat with a **thumbnail-specific goal**:
   ```
   Tool: chat_configure
   Args: {
     "notebook_id": "<id>",
     "goal": "Create a bold, visually striking infographic that highlights the single most important technical insight. Use clear icons and minimal text. Suitable as a LinkedIn post thumbnail.",
     "response_length": "concise"
   }
   ```
3. Generate: `infographic_create`
4. Poll: `studio_status`

**Option B — NotebookLM Slides (For carousel-style posts)**
1. Generate a slide deck from the research notebook
2. First slide becomes the thumbnail/hero image
3. Remaining slides become a LinkedIn carousel (PDF upload)

### Best Practices for Visual Content

| Guideline | Why |
|---|---|
| **Research first, visuals second** | Studio artifacts are only as good as the source material in the notebook |
| **Focus the notebook** | Narrow notebooks → better infographics. Don't dump 10 unrelated sources |
| **Configure chat before generating** | `chat_configure` guides tone, depth, and style of the visual output |
| **Poll patiently** | Studio generation can take 1-3 minutes. Don't retry prematurely |
| **One notebook per topic** | Separate notebooks for separate projects. Avoids content bleed |
| **Review before publishing** | Always send the visual to the user for approval before attaching to a post |

### Content Pairing Matrix

| LinkedIn Post Style | Visual Asset | NotebookLM Tool |
|---|---|---|
| Deep Dive 🔬 | Slide deck (carousel) | `slide_deck_create` |
| Storytelling 📖 | Infographic (key moments) | `infographic_create` |
| Punchy ⚡ | Single thumbnail | `infographic_create` (focused) |
| Tutorial / How-to | Step-by-step slides | `slide_deck_create` |
| Project showcase | Architecture infographic | `infographic_create` |

---

## Fallback Behavior
If NotebookLM MCP is unavailable, times out, or returns an error:
1. **Research fallback**: Analyze directly using LLM context (for documents <4000 tokens)
2. **Visual fallback**: Inform the user:
   > "NotebookLM studio tidak tersedia saat ini. Anda bisa membuat visual secara manual menggunakan Canva atau Gamma.app, dan saya bisa menyiapkan konten teksnya."

## Context Window Management
- **Use NotebookLM for**: Long repos (>4000 tokens), multiple sources, deep analysis
- **Analyze directly for**: Short READMEs, single-page articles, small code snippets

## Cleanup
After all artifacts are generated and the user is satisfied:
```
# Delete studio artifacts if no longer needed
Tool: studio_delete
Args: { "notebook_id": "<id>" }

# Delete the notebook
Tool: notebook_delete
Args: { "notebook_id": "<id>" }
```
