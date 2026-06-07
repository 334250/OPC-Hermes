---
name: opc-webui-designer
description: OPC-Hermes WebUI designer skill powered by taste-skill — anti-slop premium frontend design for dashboards, data tables, and multi-step product UI. Adapts taste-skill's design dials for data-dense OPC interfaces.
---

# OPC WebUI Designer — Anti-Slop Dashboard & Product UI Skill

> Dashboard, data tables, multi-step product UI — NOT landing pages.
> Built on taste-skill's design principles, adapted for OPC-Hermes operational interfaces.

## 0. DESIGN READ (Dashboard Context)

OPC-Hermes WebUI is a **multi-agent operations dashboard** — not a marketing site:
- **Page kind**: Operational dashboard + admin panel + data explorer
- **Audience**: Developers and power users managing AI agent teams
- **Vibe**: Premium developer tool (Linear / Vercel / Railway quality)
- **Constraints**: Data-dense but not cluttered, dark-first, responsive

### 0.A Core Design Direction
- **VARIANCE: 5** — structured layouts for data clarity (not artsy)
- **MOTION: 4** — subtle transitions, no cinematic effects
- **DENSITY: 6** — dashboard density with breathing room

### 0.B Technology Stack
- React 18 + TypeScript + Vite
- Tailwind CSS with custom OPC palette
- React Router for page navigation
- React Flow for DAG visualization
- ECharts for charts/metrics
- Lucide React for icons
- Geist font family

## 1. COLOR SYSTEM (OPC Dark)

```
Background:  #0a0a0f (deep space)
Surface:     #14141f (card bg)
Surface 2:   #1e1e2e (hover/active)
Border:      #2a2a3a (subtle)
Text:        #e4e4ec (primary)
Text 2:      #8888a0 (secondary)
Accent:      #7c3aed (OPC purple)
Success:     #22c55e
Warning:     #f59e0b
Error:       #ef4444
```

## 2. LAYOUT ARCHITECTURE

```
┌──────────────────────────────────────────┐
│  Sidebar (240px)    │  Main Content       │
│  ┌──────────────┐   │  ┌──────────────┐   │
│  │ Logo + Nav   │   │  │ Page Header  │   │
│  │              │   │  │              │   │
│  │ - Dashboard  │   │  │ Content Area │   │
│  │ - Agents     │   │  │              │   │
│  │ - Tasks      │   │  │              │   │
│  │ - Memory     │   │  │              │   │
│  │ - Artifacts  │   │  │              │   │
│  │ - Proposals  │   │  │              │   │
│  │ - Config     │   │  │              │   │
│  └──────────────┘   │  └──────────────┘   │
└──────────────────────────────────────────┘
```

## 3. COMPONENT SPECIFICATION

### 3.A Sidebar
- Fixed 240px left sidebar with logo + icon navigation
- Active state: accent left border + subtle bg highlight
- Collapse toggle for narrow screens
- Bottom: user + settings

### 3.B Cards
- Rounded-xl (12px), surface bg, 1px border
- Hover: border accent, subtle shadow glow
- Headers: uppercase tracking label + value
- Content: clean typography, no clutter

### 3.C Data Tables
- Alternating row colors (surface / surface-2)
- Sticky headers with bottom border
- Row hover highlight
- Sortable column headers
- Empty state with illustration + CTA

### 3.D DAG Visualization (React Flow)
- Custom node: rounded card with worker icon + status badge
- Custom edge: animated dash for in-progress, solid for complete
- Auto-layout with dagre
- Minimap in bottom-right corner

### 3.E Status Badges
```
completed → green dot + "Completed"
running   → yellow pulse + "Running"  
failed    → red dot + "Failed"
pending   → gray dot + "Pending"
```

## 4. PAGE SPECIFICATIONS

### 4.A Dashboard (`/`)
- Top: 4 stat cards (Active Tasks, Workers, Avg Quality, Proposals)
- Middle-left: Recent Tasks list (last 10)
- Middle-right: Quality Trend Chart (line chart, last 30 days)
- Bottom: Pending Proposals list

### 4.B Agent List (`/agents`)
- Search bar + filter chips (role: all/leader/worker/evaluator)
- Card grid: worker card with icon, name, role badge, quality score, skill count
- Click → Agent Detail overlay with skills, scores, model, toolsets

### 4.C Task Detail (`/tasks/:taskId`)
- DAG visualization (React Flow) showing all steps
- Step detail panel: click node → show prompt, output, artifacts, scores
- Timeline: progress reports in chronological order
- Artifacts: file list with download links

### 4.D Memory Browser (`/memory`)
- Tab selector: Project | Eval | Knowledge Base
- Search input with tag filter
- Table view of entries
- Click → detail panel with full content

### 4.E Artifact Viewer (`/artifacts`)
- Task/Worker/Version breadcrumb navigation
- File preview (markdown, json, code with syntax highlight)
- Download button
- Version history list

### 4.F Proposal Review (`/proposals`)
- Status tabs: Pending | Approved | Applied
- Proposal card: title, worker, risk badge, description, evidence
- Approve/Reject buttons (pending only)

### 4.G Configuration (`/config`)
- YAML editor with syntax highlighting
- Save + validate buttons
- Config sections in collapsible accordions

## 5. ANTI-SLOP RULES (Dashboard Edition)

- Never use AI-purple gradients
- Never use centered hero layouts (this is a dashboard)
- Never use glassmorphism cards
- Never use floating blobs or orbs
- Never use generic "unleash/elevate/revolutionize" copy
- Never use fake stats or placeholder data

Instead:
- Use the OPC dark palette consistently
- Use structured grid layouts with clear hierarchy
- Use real data from the API (show "No data" when empty)
- Use precise, technical copy throughout

## 6. IMPLEMENTATION RULES

- All API calls go through `lib/api.ts` with typed responses
- Use React Query for data fetching with cache invalidation
- All components accept `className` for composition
- No inline styles — use Tailwind exclusively
- Mobile-responsive with sidebar collapse at 768px
- Loading states: skeleton cards (not spinners)
- Error states: inline error card with retry button
- Empty states: illustration + description + CTA
