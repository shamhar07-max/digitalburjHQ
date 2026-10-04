'use strict';
/* HQ Integrations: how connections are added, what is wired into HQ today, and a directory of AI tools,
   design tools, platforms and GitHub skill repos with setup notes. The directory is reference material:
   AI tools connect inside the tool itself (MCP / skills); HQ never receives their credentials. */

/* [id, name, kind, description, how to connect, url, logo (defaults to id)] */
const INTEGRATION_GROUPS = [
  ['AI assistants', [
    ['claude', 'Claude', 'Assistant', 'Drafting, analysis, files and research. Connectors let it read your tools.', 'Sign in at claude.ai, then add connectors under Settings → Connectors.', 'https://claude.ai'],
    ['chatgpt', 'ChatGPT', 'Assistant', 'General assistant for writing, data work and image generation.', 'Sign in at chatgpt.com. Add apps or connectors from Settings.', 'https://chatgpt.com'],
    ['gemini', 'Gemini', 'Assistant', 'Google’s assistant, strongest alongside Docs, Drive and Gmail.', 'Sign in with your Google Workspace account at gemini.google.com.', 'https://gemini.google.com'],
    ['copilot', 'Microsoft Copilot', 'Assistant', 'Assistant built into Windows, Edge and Microsoft 365.', 'Sign in with a Microsoft account at copilot.microsoft.com.', 'https://copilot.microsoft.com'],
    ['perplexity', 'Perplexity', 'Research', 'Web research with cited sources.', 'Sign in at perplexity.ai. Use Spaces for shared team research.', 'https://www.perplexity.ai'],
    ['grok', 'Grok', 'Assistant', 'xAI’s assistant with live X (Twitter) context.', 'Sign in at grok.com.', 'https://grok.com'],
    ['mistral', 'Le Chat (Mistral)', 'Assistant', 'European assistant from Mistral AI.', 'Sign in at chat.mistral.ai.', 'https://chat.mistral.ai'],
    ['deepseek', 'DeepSeek', 'Assistant', 'Reasoning-focused models, also available through APIs.', 'Sign in at chat.deepseek.com, or create an API key on the platform.', 'https://chat.deepseek.com'],
    ['qwen', 'Qwen', 'Assistant', 'Alibaba’s open-weight models and chat app.', 'Sign in at chat.qwen.ai, or run open weights through Ollama.', 'https://chat.qwen.ai'],
    ['kimi', 'Kimi', 'Assistant', 'Moonshot AI’s assistant with long-context reading.', 'Sign in at kimi.com.', 'https://www.kimi.com']
  ]],
  ['Coding agents & editors', [
    ['claudecode', 'Claude Code', 'CLI agent', 'Anthropic’s terminal coding agent. Reads the repo, edits files, runs tests.', 'Run `npm install -g @anthropic-ai/claude-code`, then `claude`. Add tools with `claude mcp add`.', 'https://claude.com/claude-code'],
    ['opencode', 'OpenCode', 'CLI agent', 'Open-source terminal coding agent that works with many model providers.', 'Run `curl -fsSL https://opencode.ai/install | bash`, then `opencode auth login`. MCP servers go in `opencode.json`.', 'https://opencode.ai'],
    ['codex', 'OpenAI Codex CLI', 'CLI agent', 'OpenAI’s open-source coding agent for the terminal.', 'Run `npm install -g @openai/codex`, then `codex` and sign in with ChatGPT or an API key.', 'https://github.com/openai/codex'],
    ['geminicli', 'Gemini CLI', 'CLI agent', 'Google’s open-source terminal agent.', 'Run `npm install -g @google/gemini-cli`, then `gemini` and sign in with Google.', 'https://github.com/google-gemini/gemini-cli'],
    ['githubcopilot', 'GitHub Copilot', 'Editor agent', 'Code completion, chat and agent mode inside VS Code, JetBrains and GitHub.', 'Enable Copilot for the organisation in GitHub settings, then install the editor extension.', 'https://github.com/features/copilot'],
    ['cursor', 'Cursor', 'AI editor', 'VS Code–based editor with agent and codebase chat.', 'Install the editor and sign in. Add MCP servers in Settings → MCP.', 'https://cursor.com'],
    ['windsurf', 'Windsurf', 'AI editor', 'AI editor with the Cascade agent.', 'Install the editor and sign in. MCP servers are added in Cascade settings.', 'https://windsurf.com'],
    ['cline', 'Cline', 'Editor agent', 'Open-source coding agent as a VS Code extension.', 'Install “Cline” from the VS Code marketplace and add your model API key.', 'https://cline.bot'],
    ['roocode', 'Roo Code', 'Editor agent', 'Open-source agent extension for VS Code with custom modes.', 'Install “Roo Code” from the VS Code marketplace and add a model provider.', 'https://roocode.com'],
    ['kilocode', 'Kilo Code', 'Editor agent', 'Open-source coding agent for VS Code and JetBrains.', 'Install the extension and pick a model provider.', 'https://kilo.ai'],
    ['trae', 'Trae', 'AI editor', 'ByteDance’s AI-native editor.', 'Download from trae.ai and sign in.', 'https://www.trae.ai'],
    ['amp', 'Amp', 'CLI agent', 'Sourcegraph’s coding agent for terminal and editor.', 'Install from ampcode.com and sign in.', 'https://ampcode.com'],
    ['devin', 'Devin', 'Cloud agent', 'Autonomous software engineer that works from tickets and repos.', 'Create a workspace at devin.ai and connect GitHub.', 'https://devin.ai'],
    ['aider', 'Aider', 'CLI agent', 'Open-source pair-programming tool that edits your git repo from the terminal.', 'Follow the install steps on aider.chat, then run `aider` inside the repo.', 'https://aider.chat'],
    ['jetbrains', 'JetBrains AI', 'IDE', 'AI assistance in IntelliJ, PyCharm, WebStorm and other JetBrains IDEs.', 'Enable the AI Assistant plugin in the IDE and sign in.', 'https://www.jetbrains.com/ai/'],
    ['replit', 'Replit', 'Cloud IDE', 'Browser IDE with an agent that can build and host apps.', 'Sign in at replit.com and import the GitHub repo.', 'https://replit.com'],
    ['lovable', 'Lovable', 'App builder', 'Generates web apps from prompts and syncs them to GitHub.', 'Sign in at lovable.dev and connect GitHub.', 'https://lovable.dev'],
    ['bolt', 'Bolt', 'App builder', 'Prompt-to-app builder that runs in the browser.', 'Sign in at bolt.new.', 'https://bolt.new'],
    ['v0', 'v0', 'UI builder', 'Vercel’s generator for UI components and pages.', 'Sign in at v0.app. Deploy straight to Vercel.', 'https://v0.app']
  ]],
  ['Skills, MCP & GitHub repos', [
    ['mcp', 'Model Context Protocol', 'Standard', 'The open standard that lets AI tools call your apps and data through small servers.', 'Add a server URL or command in your AI tool’s MCP settings. Prefer read-only tokens.', 'https://modelcontextprotocol.io'],
    ['claude', 'Anthropic Skills', 'GitHub repo', 'Official example Agent Skills for Claude: documents, spreadsheets, design and more.', 'In Claude Code run `/plugin marketplace add anthropics/skills`, then install the skills you want.', 'https://github.com/anthropics/skills', 'claude'],
    ['gstack', 'gstack', 'GitHub repo', 'A suite of role-based slash-command skills for Claude Code: planning, review, QA and shipping.', 'Clone it into `~/.claude/skills` and run the setup described in the repo README.', 'https://github.com/garrytan/gstack'],
    ['impeccable', 'Impeccable', 'GitHub repo', 'Design-quality skills that steer coding agents away from generic UI.', 'Install it for your tool from impeccable.style or the repo README.', 'https://impeccable.style'],
    ['superpowers', 'Superpowers', 'GitHub repo', 'Skills for planning, test-driven development and code review in coding agents.', 'Install as a Claude Code plugin; the steps are in the repo README.', 'https://github.com/obra/superpowers'],
    ['speckit', 'Spec Kit', 'GitHub repo', 'GitHub’s toolkit for spec-driven development with AI agents.', 'Run `uvx --from git+https://github.com/github/spec-kit.git specify init <project>`.', 'https://github.com/github/spec-kit'],
    ['github', 'GitHub MCP Server', 'GitHub repo', 'Lets AI tools read repos, issues and pull requests.', 'Add the server to your AI tool with a fine-grained token limited to the repos you choose.', 'https://github.com/github/github-mcp-server'],
    ['playwright', 'Playwright MCP', 'GitHub repo', 'Gives agents a real browser to test and screenshot pages.', 'Add the MCP command `npx @playwright/mcp@latest` to your AI tool.', 'https://github.com/microsoft/playwright-mcp'],
    ['context7', 'Context7', 'GitHub repo', 'Feeds current library documentation into prompts.', 'Add the MCP command `npx -y @upstash/context7-mcp` to your AI tool.', 'https://github.com/upstash/context7'],
    ['firecrawl', 'Firecrawl MCP', 'GitHub repo', 'Web scraping and search for agents.', 'Add the Firecrawl MCP server with your Firecrawl API key.', 'https://github.com/firecrawl/firecrawl-mcp-server'],
    ['mcp', 'Reference MCP servers', 'GitHub repo', 'Official reference servers: filesystem, git, fetch, memory and more.', 'Run a server with `npx` or `uvx` as listed in the repo, then add it to your AI tool.', 'https://github.com/modelcontextprotocol/servers', 'mcp'],
    ['awesome', 'Awesome MCP Servers', 'GitHub list', 'Community-curated list of MCP servers by category.', 'Browse for a server, review its code, then add it to your AI tool.', 'https://github.com/punkpeye/awesome-mcp-servers'],
    ['awesome', 'Awesome Claude Skills', 'GitHub list', 'Community-curated Claude skills and resources.', 'Browse, review the source of any skill, then copy it into `~/.claude/skills`.', 'https://github.com/ComposioHQ/awesome-claude-skills', 'awesome']
  ]],
  ['Design & creative', [
    ['canva', 'Canva', 'Design', 'Presentations, social posts and brand kits.', 'Sign in at canva.com. Connect it to your AI assistant from the assistant’s connectors list.', 'https://www.canva.com'],
    ['figma', 'Figma', 'Design', 'Interface design and design systems. An MCP server exposes frames to coding agents.', 'Sign in at figma.com. Enable the Figma MCP server in Dev Mode for your coding agent.', 'https://www.figma.com'],
    ['adobe', 'Adobe', 'Design', 'Photoshop, Illustrator, Express and Acrobat.', 'Sign in with an Adobe ID at adobe.com.', 'https://www.adobe.com'],
    ['midjourney', 'Midjourney', 'Images', 'Image generation for concepts and campaigns.', 'Sign in at midjourney.com.', 'https://www.midjourney.com'],
    ['elevenlabs', 'ElevenLabs', 'Voice', 'Text-to-speech and voice cloning.', 'Create an account and an API key at elevenlabs.io.', 'https://elevenlabs.io'],
    ['stability', 'Stability AI', 'Images', 'Stable Diffusion models and APIs.', 'Create an API key at platform.stability.ai.', 'https://stability.ai'],
    ['runway', 'Runway', 'Video', 'AI video generation and editing.', 'Sign in at runwayml.com.', 'https://runwayml.com'],
    ['descript', 'Descript', 'Video', 'Edit audio and video by editing text.', 'Sign in at descript.com.', 'https://www.descript.com'],
    ['framer', 'Framer', 'Websites', 'Design and publish marketing sites.', 'Sign in at framer.com.', 'https://www.framer.com'],
    ['webflow', 'Webflow', 'Websites', 'Visual website builder with a CMS.', 'Sign in at webflow.com.', 'https://webflow.com'],
    ['miro', 'Miro', 'Whiteboard', 'Collaborative whiteboards for planning and workshops.', 'Sign in at miro.com.', 'https://miro.com'],
    ['unsplash', 'Unsplash', 'Photos', 'Free stock photography.', 'Browse at unsplash.com. Check each photo’s licence.', 'https://unsplash.com'],
    ['lottiefiles', 'LottieFiles', 'Motion', 'Lightweight animations for web and apps.', 'Sign in at lottiefiles.com.', 'https://lottiefiles.com']
  ]],
  ['Models, runtimes & automation', [
    ['openrouter', 'OpenRouter', 'Model API', 'One API key for many hosted models.', 'Create a key at openrouter.ai and set it as the provider key in your tool.', 'https://openrouter.ai'],
    ['huggingface', 'Hugging Face', 'Model hub', 'Open models, datasets and Spaces.', 'Create an account and a read-only access token at huggingface.co.', 'https://huggingface.co'],
    ['ollama', 'Ollama', 'Local models', 'Run open models on your own machine.', 'Install from ollama.com, then `ollama run <model>`.', 'https://ollama.com'],
    ['lmstudio', 'LM Studio', 'Local models', 'Desktop app for running local models with an OpenAI-compatible server.', 'Download from lmstudio.ai and start the local server.', 'https://lmstudio.ai'],
    ['groq', 'Groq', 'Model API', 'Very fast hosted inference for open models.', 'Create an API key at console.groq.com.', 'https://groq.com'],
    ['zapier', 'Zapier', 'Automation', 'Connects thousands of apps without code.', 'Sign in at zapier.com and build a Zap. Use a webhook step to reach HQ.', 'https://zapier.com'],
    ['make', 'Make', 'Automation', 'Visual workflow automation.', 'Sign in at make.com and build a scenario.', 'https://www.make.com'],
    ['n8n', 'n8n', 'Automation', 'Open-source, self-hostable workflow automation.', 'Self-host with Docker or use n8n Cloud.', 'https://n8n.io'],
    ['dify', 'Dify', 'Agent builder', 'Open-source platform for building LLM apps and agents.', 'Use Dify Cloud or self-host with Docker.', 'https://dify.ai'],
    ['langchain', 'LangChain', 'Framework', 'Libraries for building LLM applications.', 'Install with `pip install langchain` or `npm install langchain`.', 'https://www.langchain.com'],
    ['llamaindex', 'LlamaIndex', 'Framework', 'Data framework for retrieval-augmented apps.', 'Install with `pip install llama-index`.', 'https://www.llamaindex.ai'],
    ['comfyui', 'ComfyUI', 'Images', 'Node-based workflows for image and video models.', 'Install from comfy.org and run locally.', 'https://www.comfy.org']
  ]],
  ['Platform & developer services', [
    ['github', 'GitHub', 'Code', 'Source, pull requests and CI for HQ.', 'Repo access is managed on GitHub. Use fine-grained tokens for tools.', 'https://github.com'],
    ['gitlab', 'GitLab', 'Code', 'Git hosting and CI/CD.', 'Create a project access token with the smallest scope needed.', 'https://gitlab.com'],
    ['vercel', 'Vercel', 'Hosting', 'Hosting and previews for front-end sites.', 'Import a repo at vercel.com. An MCP server is available for AI tools.', 'https://vercel.com'],
    ['railway', 'Railway', 'Hosting', 'Hosts the HQ web app, mail worker and nightly backup.', 'Services and variables are managed in the Railway project.', 'https://railway.com'],
    ['supabase', 'Supabase', 'Database', 'Postgres database behind HQ, with row-level security.', 'Connection string is stored as `DATABASE_URL` on the server. An MCP server is at `https://mcp.supabase.com/mcp`.', 'https://supabase.com'],
    ['cloudflare', 'Cloudflare', 'Network & storage', 'DNS for hq.digitalburj.com and R2 object storage.', 'R2 keys are server variables (`R2_*`). DNS is managed in the Cloudflare dashboard.', 'https://www.cloudflare.com'],
    ['sentry', 'Sentry', 'Monitoring', 'Error tracking and performance monitoring.', 'Create a project at sentry.io and add its DSN to the app.', 'https://sentry.io'],
    ['postman', 'Postman', 'API', 'Design and test APIs.', 'Sign in at postman.com and import the API.', 'https://www.postman.com'],
    ['docker', 'Docker', 'Containers', 'Container builds. HQ ships as a Docker image.', 'Install Docker Desktop and run `docker build -t hq .`.', 'https://www.docker.com'],
    ['stripe', 'Stripe', 'Payments', 'Checkout and payment webhooks for affiliate sales.', 'Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` on the server.', 'https://stripe.com'],
    ['resend', 'Resend', 'Email', 'Sends HQ invitations and password-reset emails.', 'SMTP credentials are server variables (`SMTP_*`).', 'https://resend.com'],
    ['twilio', 'Twilio', 'Messaging', 'SMS, WhatsApp and voice.', 'Create an account and API credentials at twilio.com.', 'https://www.twilio.com'],
    ['googlecloud', 'Google Cloud', 'Cloud', 'Google’s cloud platform and OAuth credentials.', 'Create OAuth credentials in the Cloud console for Google Meet.', 'https://cloud.google.com'],
    ['aws', 'AWS', 'Cloud', 'Amazon’s cloud platform.', 'Use IAM users or roles with least privilege.', 'https://aws.amazon.com'],
    ['azure', 'Microsoft Azure', 'Cloud', 'Microsoft’s cloud platform, including Azure OpenAI.', 'Create a resource group and use managed identities where possible.', 'https://azure.microsoft.com'],
    ['nvidia', 'NVIDIA Build', 'Model API', 'Hosted model endpoints from NVIDIA.', 'Create an API key at build.nvidia.com.', 'https://build.nvidia.com']
  ]],
  ['Workspace & communication', [
    ['googlemeet', 'Google Meet', 'Meetings', 'Meeting links created from HQ’s Meetings page.', 'An owner clicks Connect Google Meet on this page after server credentials are set.', 'https://meet.google.com'],
    ['google', 'Google Workspace', 'Suite', 'Gmail, Calendar, Drive, Docs and Sheets.', 'Sign in with the company Google account.', 'https://workspace.google.com'],
    ['googledrive', 'Google Drive', 'Files', 'Shared drives for large or external files.', 'Use shared drives, and link files from HQ Documents.', 'https://drive.google.com'],
    ['gmail', 'Gmail', 'Email', 'Company mailboxes.', 'Sign in with the company Google account.', 'https://mail.google.com'],
    ['slack', 'Slack', 'Chat', 'Team chat with app integrations.', 'Create a Slack app or incoming webhook for notifications.', 'https://slack.com'],
    ['teams', 'Microsoft Teams', 'Chat', 'Chat and meetings in Microsoft 365.', 'Sign in with a Microsoft 365 account.', 'https://www.microsoft.com/microsoft-teams'],
    ['zoom', 'Zoom', 'Meetings', 'Video meetings and webinars.', 'Sign in at zoom.com.', 'https://zoom.com'],
    ['notion', 'Notion', 'Docs', 'Wikis, notes and light databases.', 'Create an integration token and share pages with it.', 'https://www.notion.com'],
    ['linear', 'Linear', 'Planning', 'Issue tracking for product teams.', 'Create a personal API key under Settings → API.', 'https://linear.app'],
    ['airtable', 'Airtable', 'Databases', 'Spreadsheet-style databases.', 'Create a personal access token with limited scopes.', 'https://airtable.com'],
    ['hubspot', 'HubSpot', 'CRM', 'CRM, marketing and sales tools.', 'Create a private app token with the scopes you need.', 'https://www.hubspot.com'],
    ['typeform', 'Typeform', 'Forms', 'Forms and surveys.', 'Create a personal access token at typeform.com.', 'https://www.typeform.com'],
    ['monday', 'monday.com', 'Planning', 'Work management boards.', 'Create an API token from your profile.', 'https://monday.com'],
    ['asana', 'Asana', 'Planning', 'Task and project management.', 'Create a personal access token in the developer console.', 'https://asana.com'],
    ['trello', 'Trello', 'Planning', 'Kanban boards.', 'Create an API key and token at trello.com/power-ups/admin.', 'https://trello.com'],
    ['clickup', 'ClickUp', 'Planning', 'Tasks, docs and goals in one place.', 'Create a personal API token in settings.', 'https://clickup.com']
  ]]
];

const INTEGRATION_LIVE = [
  ['supabase', 'Supabase Postgres', 'Stores every record: people, jobs, messages, documents.', '`DATABASE_URL` (server variable). Row-level security on every table.', ''],
  ['cloudflare', 'Cloudflare R2', 'Holds documents and encrypted nightly backups in two separate buckets.', '`R2_ACCOUNT_ID`, `R2_FILES_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.', ''],
  ['resend', 'Resend email', 'Sends invitations, password resets and verification links.', '`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`.', ''],
  ['railway', 'Railway hosting', 'Runs the web app, mail worker and the nightly backup job.', 'Services and variables in the Railway project.', ''],
  ['github', 'GitHub', 'Source code, CI tests and the Android app builds.', 'Repository settings and Actions workflows.', ''],
  ['googlemeet', 'Google Meet', 'Creates meeting links when staff schedule meetings.', 'Server: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`. Owner then clicks Connect below.', 'google'],
  ['stripe', 'Stripe', 'Checkout for affiliate sales and signed payment webhooks.', 'Server: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`.', 'stripe']
];

const Integ = { q: '', cat: 'All' };

function integMark(text) {
  return esc(text).replace(/`([^`]+)`/g, '<code>$1</code>');
}
function integCard(t) {
  const logo = t[6] || t[0];
  return `<article class="int-card"><img class="int-logo" src="${esc('logos/' + logo + '.svg')}" alt="" width="40" height="40" loading="lazy">
<div class="int-body"><div class="int-head"><h3>${esc(t[1])}</h3><span class="chip">${esc(t[2])}</span></div><p>${esc(t[3])}</p>
<details><summary>How to connect</summary><p>${integMark(t[4])}</p></details></div>
<a class="int-open" href="${esc(t[5])}" target="_blank" rel="noopener noreferrer" aria-label="Open ${esc(t[1])} (opens in a new tab)">${ico('arrowRight', 'sm')}</a></article>`;
}
function integFiltered() {
  const q = Integ.q.trim().toLowerCase();
  return INTEGRATION_GROUPS
    .filter(([g]) => Integ.cat === 'All' || Integ.cat === g)
    .map(([g, list]) => [g, list.filter(t => !q || (t[1] + ' ' + t[2] + ' ' + t[3] + ' ' + g).toLowerCase().includes(q))])
    .filter(([, list]) => list.length);
}
function integGrid() {
  const groups = integFiltered();
  if (!groups.length) return '<div class="empty">Nothing matches that search.</div>';
  return groups.map(([g, list]) => `<section class="int-group"><h3 class="int-group-title">${esc(g)} <small>${list.length}</small></h3><div class="int-grid">${list.map(integCard).join('')}</div></section>`).join('');
}
function integTotal() { return INTEGRATION_GROUPS.reduce((n, [, l]) => n + l.length, 0); }

function integrationsDirectoryView() {
  const how = `<div class="how-grid">
<div class="how"><span class="how-n">1</span><h3>Platform services</h3><p>Databases, storage, email and payments are connected on the server with environment variables. The HQ owner adds the credentials in Railway, redeploys, and the feature switches on. Nothing secret is ever typed into this page.</p></div>
<div class="how"><span class="how-n">2</span><h3>Sign-in connections</h3><p>Google Meet uses OAuth. After the server has the Google client credentials, the owner clicks <b>Connect Google Meet</b> below and approves access once.</p></div>
<div class="how"><span class="how-n">3</span><h3>Division apps & payments</h3><p>Academy, Business OS, Studio and Stripe send signed events to HQ. Each request carries an HMAC signature and a timestamp, and HQ rejects anything older than five minutes or unsigned.</p></div>
<div class="how"><span class="how-n">4</span><h3>AI tools & skills</h3><p>These connect inside the AI tool, not inside HQ, using MCP servers or skill folders. HQ never sees their keys. Give each tool its own least-privilege token, read-only where possible, and revoke it when someone leaves.</p></div>
</div>`;
  const live = `<div class="live-grid">${INTEGRATION_LIVE.map(([id, name, what, how, logo]) => `<article class="live-int"><img class="int-logo" src="${esc('logos/' + (logo || id) + '.svg')}" alt="" width="36" height="36"><div><div class="int-head"><h3>${esc(name)}</h3><span class="chip ok" data-live="${esc(id)}">${id === 'googlemeet' || id === 'stripe' ? 'Checking…' : 'In use'}</span></div><p>${esc(what)}</p><p class="int-how">${integMark(how)}</p></div></article>`).join('')}</div>`;
  const chips = ['All', ...INTEGRATION_GROUPS.map(([g]) => g)].map(c => `<button class="chip-btn ${Integ.cat === c ? 'on' : ''}" data-int-cat="${esc(c)}">${esc(c)}</button>`).join('');
  return panel('How integrations are added', `<div class="panel-body">${how}</div>`)
    + panel('Connected to HQ today', `<div class="panel-body">${live}</div>`)
    + `<div class="section-head"><div><h2>Tool directory</h2><small class="muted"><span id="int-count">${integTotal()}</span> AI tools, design tools, platforms and GitHub skill repos, each with a setup note. Names and logos belong to their owners.</small></div></div>
<div class="int-tools"><div class="docs-search int-search">${ico('search', 'sm')}<input id="int-q" type="search" placeholder="Search tools, e.g. OpenCode, Canva, skills" value="${esc(Integ.q)}" aria-label="Search integrations"></div><div class="chips" id="int-chips">${chips}</div></div>
<div id="int-list">${integGrid()}</div>`;
}

/* Compose with the existing live-connection panels (Google Meet controls and division records). */
const integrationsLivePanels = featureViews.integrations;
featureViews.integrations = () => title('Connections / Integrations', 'Everything HQ connects to.', 'What is wired in today, how connections are added, and the AI and design tools your team can use.')
  + integrationsDirectoryView()
  + integrationsLivePanels().replace(/^[\s\S]*?(<section class="panel"|<div class="panel")/, '$1');

const featureBindBeforeIntegrations = featureBind;
featureBind = function () {
  featureBindBeforeIntegrations();
  if (page !== 'integrations') return;
  const list = $('#int-list'), count = $('#int-count');
  const paint2 = () => {
    list.innerHTML = integGrid();
    count.textContent = integFiltered().reduce((n, [, l]) => n + l.length, 0);
    $$('[data-int-cat]').forEach(b => b.classList.toggle('on', b.dataset.intCat === Integ.cat));
  };
  $('#int-q').oninput = e => { Integ.q = e.target.value; paint2(); };
  $$('[data-int-cat]').forEach(b => b.onclick = () => { Integ.cat = b.dataset.intCat; paint2(); });
  const setChip = (id, text, ok) => { const el = $(`[data-live="${id}"]`); if (el) { el.textContent = text; el.classList.toggle('ok', !!ok); el.classList.toggle('warn', !ok); } };
  if (demo) { setChip('googlemeet', 'Preview', false); setChip('stripe', 'Preview', false); return; }
  fetch('/api/integrations').then(r => r.json()).then(d => {
    setChip('googlemeet', d.google_connected ? 'Connected' : d.google_configured ? 'Ready to connect' : 'Needs credentials', d.google_connected);
    setChip('stripe', d.stripe_configured ? 'Configured' : 'Needs credentials', d.stripe_configured);
  }).catch(() => { setChip('googlemeet', 'Unavailable', false); setChip('stripe', 'Unavailable', false); });
};
