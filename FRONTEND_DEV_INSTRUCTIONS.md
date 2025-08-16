# Frontend Developer Instructions - Knowledge Analytics System
**Project:** Meeting-Ops Knowledge Intelligence UI  
**Focus:** Speaker networks, semantic search, cross-meeting memory interface

---

## 🎯 Mission: Build Knowledge Intelligence UI

You're building the frontend for a **knowledge intelligence system** that helps users explore relationships, topics, and insights across all meetings - not just basic analytics charts.

### User Goals:
- **Find Information**: "What did John say about the budget?"
- **Discover Relationships**: "Who usually talks to Sarah in meetings?"
- **Track Topics**: "Show all discussions about Project X"
- **Connect Meetings**: "What meetings are related to this one?"
- **Organizational Memory**: "What decisions were made about security?"

---

## 📋 Your Task List (4-5 hours)

### Priority 1: Knowledge Search Interface (2 hours)
Enhance `/frontend/src/pages/Analytics.tsx`:

```typescript
// Replace basic charts with knowledge interface:

1. **Global Search Bar** (top of page)
   - Large search input: "Search across all meetings..."
   - Real-time suggestions as user types
   - Search results show: session title, speaker, relevant text snippet
   - Click result → jump to that session/timestamp

2. **Quick Filters**
   - Speaker filter: "Show only meetings with John"
   - Date range: "Last 30 days"  
   - Topic tags: "Budget", "Security", "Project X"
   - Meeting type: "All-hands", "1:1", "Team meeting"

3. **Search Results View**
   - Card layout showing matching meetings
   - Highlight matched text snippets
   - Show relevance score (0-100%)
   - "More from this meeting" expansion
```

### Priority 2: Speaker Network Visualization (1.5 hours)
Create `/frontend/src/components/SpeakerNetworkGraph.tsx`:

```typescript
// Use react-force-graph or similar for network visualization

interface NetworkNode {
  id: string;        // speaker name
  name: string;      // display name
  meetings: number;  // total meetings attended
  role?: string;     // optional: team, department
}

interface NetworkEdge {
  source: string;    // speaker 1
  target: string;    // speaker 2  
  weight: number;    // co-attendance frequency
  meetings: string[]; // shared meeting IDs
}

// Features to build:
- Interactive network graph
- Node size = number of meetings
- Edge thickness = collaboration frequency  
- Click node → filter to that speaker's meetings
- Click edge → show shared meetings
- Hover for quick stats
```

### Priority 3: Related Meetings Widget (1 hour)
Enhance `/frontend/src/pages/SessionDetails.tsx`:

```typescript
// Add new section: "Related Meetings"

interface RelatedMeeting {
  id: string;
  title: string;
  date: string;
  similarity: number;  // 0-1 similarity score
  reason: string;      // "Similar speakers", "Same topic", "Follow-up"
}

// Features:
- Shows 3-5 related meetings  
- Similarity percentage (85% similar)
- One-click navigation to related session
- "Why is this related?" explanation
- "Show more related" expansion
```

### Priority 4: Topic Tags & Clustering (30 minutes)
Create `/frontend/src/components/TopicTags.tsx`:

```typescript
// Auto-generated topic tags for meetings

interface TopicCluster {
  name: string;        // "Budget Planning"
  meetings: string[];  // session IDs in this cluster
  keywords: string[];  // key terms that define this topic
  color: string;       // consistent color for this topic
}

// Features:
- Topic tags on each session card
- Click tag → see all meetings with that topic
- Topic cloud view showing popular topics
- Color-coded consistency across UI
```

### Priority 5: Cross-Meeting Action Items (1 hour)
Create `/frontend/src/pages/ActionItems.tsx`:

```typescript
// Global action items view across all meetings

interface ActionItem {
  id: string;
  text: string;
  owner: string;
  priority: "high" | "medium" | "low";
  status: "open" | "in_progress" | "completed";
  source_session: string;
  created_date: string;
  due_date?: string;
  related_items?: string[]; // linked action items
}

// Features:
- Group by owner: "Sarah's Action Items"
- Filter by status: "All Open Items"
- Link related items: "This relates to item from last week"
- Progress tracking: "15 completed, 8 in progress, 3 overdue"
```

---

## 🎨 UI/UX Design Guidelines

### Search Interface Design
```css
/* Large, prominent search bar */
.knowledge-search {
  @apply w-full max-w-4xl mx-auto;
  @apply bg-gray-800 border border-gray-600 rounded-lg;
  @apply text-lg px-6 py-4;
  @apply focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20;
}

/* Search result cards */
.search-result {
  @apply bg-gray-800 rounded-lg p-4 border border-gray-700;
  @apply hover:border-purple-500 transition-colors cursor-pointer;
}
```

### Speaker Network Colors
```typescript
const speakerColors = {
  "high-activity": "#8B5CF6",    // Purple for frequent speakers
  "medium-activity": "#06B6D4",  // Cyan for regular speakers  
  "low-activity": "#6B7280",     // Gray for occasional speakers
};
```

### Topic Tag Colors
```typescript
const topicColors = [
  "#EF4444", "#F97316", "#EAB308", "#22C55E", 
  "#06B6D4", "#3B82F6", "#8B5CF6", "#EC4899"
];
```

---

## 🔌 API Integration Points

### Replace these localStorage calls with real APIs:

```typescript
// 1. Knowledge Search
const searchResults = await fetch(
  `/api/knowledge/search?query=${query}&limit=10`
).then(r => r.json());

// 2. Speaker Network  
const networkData = await fetch(
  `/api/knowledge/speakers/network`
).then(r => r.json());

// 3. Related Meetings
const relatedMeetings = await fetch(
  `/api/knowledge/related/${sessionId}`
).then(r => r.json());

// 4. Topic Clusters
const topicClusters = await fetch(
  `/api/knowledge/topics/clusters`  
).then(r => r.json());

// 5. Cross-meeting Action Items
const allActionItems = await fetch(
  `/api/knowledge/action-items/all`
).then(r => r.json());
```

---

## 🔄 Coordination with Backend

### Monitor COORDINATION.md every minute for:
- API endpoints marked as READY
- Backend requests for UI changes
- Integration test requirements

### Update COORDINATION.md when you:
1. Complete a major UI component
2. Need backend API changes  
3. Ready to test integration
4. Encounter blockers

### Testing Protocol
```typescript
// Test each feature as backend APIs become available:

// 1. First test with mock data
const mockSearchResults = [
  {session_id: "123", text: "Budget discussion...", score: 0.8}
];

// 2. Then integrate real API
const realResults = await api.knowledge.search(query);

// 3. Verify UI handles edge cases:
- Empty search results
- Network with 1 speaker  
- Sessions with no related meetings
- Very long topic names
```

---

## 📊 Component Architecture

### Page Structure
```
Analytics.tsx (main page)
├── KnowledgeSearch.tsx (search bar + results)
├── SpeakerNetworkGraph.tsx (network visualization)  
├── TopicClusters.tsx (topic cloud)
└── QuickStats.tsx (summary metrics)

SessionDetails.tsx (individual session)
├── [existing components]
├── RelatedMeetings.tsx (similar sessions)
└── TopicTags.tsx (topic labels)

ActionItems.tsx (new page)  
├── ActionItemsTable.tsx (sortable table)
├── ActionItemFilters.tsx (filter controls)
└── ActionItemStats.tsx (progress metrics)
```

### State Management
```typescript
// Use React context for knowledge data
interface KnowledgeContextType {
  searchQuery: string;
  searchResults: SearchResult[];
  selectedSpeaker: string | null;
  selectedTopic: string | null;
  networkData: NetworkData | null;
  isLoading: boolean;
}
```

---

## 🧪 Testing Checklist

### Manual Testing Scenarios:
- [ ] Search for "budget" returns relevant meetings
- [ ] Click speaker in network shows their meetings
- [ ] Related meetings make logical sense
- [ ] Topic tags are consistent across sessions
- [ ] Action items link properly across meetings
- [ ] All loading states work
- [ ] Empty states display properly
- [ ] Error handling works (API failures)

### Integration Testing:
- [ ] Search integrates with backend API
- [ ] Speaker network displays real relationship data
- [ ] Related meetings API provides sensible suggestions
- [ ] Topic clusters group meetings logically
- [ ] Cross-meeting action items load from database

---

## 🚀 Implementation Order

**Day 1 (4 hours):**
1. **Hour 1:** Build KnowledgeSearch component with mock data
2. **Hour 2:** Create SpeakerNetworkGraph component  
3. **Hour 3:** Add RelatedMeetings widget to SessionDetails
4. **Hour 4:** Build TopicTags component

**Day 2 (2 hours):**
1. **Hour 1:** Create ActionItems page
2. **Hour 2:** Integrate all components with real APIs (as they become ready)

---

## 💡 Pro Tips

### Performance Optimization:
```typescript
// Debounce search to avoid API spam
const debouncedSearch = useMemo(
  () => debounce(performSearch, 300),
  []
);

// Virtualize large lists
import { FixedSizeList as List } from 'react-window';
```

### User Experience:
```typescript
// Show loading states
{isLoading ? <Skeleton /> : <SearchResults />}

// Provide helpful empty states  
{results.length === 0 && (
  <div>No meetings found. Try different keywords.</div>
)}

// Add keyboard shortcuts
useEffect(() => {
  const handleKeyPress = (e) => {
    if (e.key === '/' && !e.target.matches('input')) {
      searchRef.current?.focus();
    }
  };
}, []);
```

---

## 🎯 Success Criteria

Your frontend is complete when:
- [ ] Users can search across all meetings and find relevant content
- [ ] Speaker network visualization shows meaningful relationships  
- [ ] Related meetings provide valuable suggestions
- [ ] Topic tags help users navigate by subject
- [ ] Action items can be tracked across multiple meetings
- [ ] All components handle loading/error states gracefully
- [ ] UI feels fast and responsive
- [ ] Integration with backend APIs works smoothly

---

## 📝 Key Considerations

- **Think like a user**: How would someone actually want to explore meeting knowledge?
- **Focus on relationships**: This is about connections between people, topics, and ideas
- **Make it discoverable**: Users should stumble upon interesting insights
- **Performance matters**: Large organizations have hundreds of meetings
- **Mobile-friendly**: Executives will use this on tablets

**File to monitor:** `/home/ucadmin/Meeting-Ops/COORDINATION.md` (check every 1 minute)

---

**Remember:** You're not building charts and graphs - you're building an intelligent interface that helps organizations discover and connect their meeting knowledge. Think "organizational brain" not "dashboard".