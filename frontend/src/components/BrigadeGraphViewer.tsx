/**
 * Brigade Phase 2 — in-page 3D graph viewer for SessionDetails.
 *
 * Renders the current meeting's Brigade nodes + 1-hop neighbors
 * (Speaker / ActionItem / Topic / Decision) as a force-directed 3D
 * graph using react-force-graph-3d (which wraps three.js under the
 * hood — ~500KB+ footprint, code-split via React.lazy in
 * SessionDetails so this only loads when the user expands the
 * Knowledge graph section).
 *
 * Data source: GET /api/sessions/{id}/brigade-graph, which queries
 * Brigade's /api/v1/knowledge/context/{name} endpoint and maps the
 * response to the {nodes, links} shape react-force-graph-3d
 * consumes. Server caches the result for 30s.
 *
 * Three rendering states:
 *   - "synced" (nodes + links populated): renders the 3D graph.
 *   - "not_synced_yet" (empty + reason='not_synced_yet'): shows the
 *     friendly "this meeting hasn't been synced yet" message. This
 *     is the expected state for new sessions and any deployment
 *     where BRIGADE_API_KEY isn't configured.
 *   - "live_failed" (empty + reason='live_failed'): synced once but
 *     Brigade is currently unreachable; shows a retry button.
 *
 * The component is internally headless on data — it owns its fetch
 * + state machine — so SessionDetails just passes sessionId and the
 * viewer handles the rest.
 */
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { config } from '../config';
import { useOrg } from '../contexts/OrgContext';

// ---------------------------------------------------------------------------
// Wire types — mirror the backend response in api/recording.py
// (get_brigade_graph). Keep these here rather than a shared types file
// so the BrigadeGraphViewer module is self-contained for the
// React.lazy code-split.
// ---------------------------------------------------------------------------

interface BrigadeNode {
  id: string;
  label: string; // "Meeting" | "Speaker" | "ActionItem" | "Topic" | "Decision" | other
  name: string;
  is_focus?: boolean;
  properties?: Record<string, unknown>;
}

interface BrigadeLink {
  source: string;
  target: string;
  type: string; // "HAS_SPEAKER" | "HAS_ACTION_ITEM" | "HAS_TOPIC" | "HAS_DECISION" | "ASSIGNED_TO" | "DECIDED_BY" | other
  properties?: Record<string, unknown>;
}

interface BrigadeGraphResponse {
  nodes: BrigadeNode[];
  links: BrigadeLink[];
  graph_url: string | null;
  focus: string | null;
  reason: 'not_synced_yet' | 'live_failed' | null;
  synced_at: string | null;
}

// ---------------------------------------------------------------------------
// Color + size maps per label. Indigo/green/orange/blue/purple per the
// spec; "other" labels (Concept, Person, etc) fall back to slate.
// ---------------------------------------------------------------------------

const LABEL_COLORS: Record<string, string> = {
  Meeting: '#6366f1', // indigo-500 — focus node
  Speaker: '#10b981', // emerald-500 — people
  ActionItem: '#f97316', // orange-500 — things to do
  Topic: '#3b82f6', // blue-500 — discussion threads
  Decision: '#a855f7', // purple-500 — outcomes
};

const LABEL_FALLBACK_COLOR = '#64748b'; // slate-500

function colorForLabel(label: string): string {
  return LABEL_COLORS[label] || LABEL_FALLBACK_COLOR;
}

function sizeForNode(node: BrigadeNode): number {
  // Meeting nodes (the focus) are visually larger so the user can
  // orient themselves at a glance.
  if (node.is_focus || node.label === 'Meeting') return 8;
  return 4;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface BrigadeGraphViewerProps {
  sessionId: string;
  height?: number;
  showLabels?: boolean;
}

const BrigadeGraphViewer: React.FC<BrigadeGraphViewerProps> = ({
  sessionId,
  height = 480,
  showLabels = true,
}) => {
  const { getOrgQueryUrl } = useOrg();
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<unknown>(null);

  const [data, setData] = useState<BrigadeGraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [containerWidth, setContainerWidth] = useState<number>(0);
  const [selectedNode, setSelectedNode] = useState<BrigadeNode | null>(null);

  // Measure container width so the canvas fits its parent on resize.
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const update = () => setContainerWidth(el.clientWidth);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('access_token');
      const url = getOrgQueryUrl(
        `${config.apiUrl}/api/sessions/${sessionId}/brigade-graph`,
      );
      const resp = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${text.slice(0, 200)}`);
      }
      const body: BrigadeGraphResponse = await resp.json();
      setData(body);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [sessionId, getOrgQueryUrl]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  // react-force-graph-3d wants nodes + links to be REFERENCES that
  // match (link.source === node.id). We pass the response shape
  // directly; the library does its own resolution. But on re-render
  // we must avoid mutating the same array (the library stores
  // simulation state on the objects) so we memoize a per-fetch copy.
  const graphData = useMemo(() => {
    if (!data || !data.nodes.length) {
      return { nodes: [], links: [] };
    }
    return {
      nodes: data.nodes.map((n) => ({ ...n })),
      links: data.links.map((l) => ({ ...l })),
    };
  }, [data]);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  if (loading) {
    return (
      <div
        ref={containerRef}
        className="bg-slate-50 border border-slate-200 rounded-lg p-6 flex items-center justify-center"
        style={{ height }}
      >
        <div className="flex items-center gap-3 text-slate-600 text-sm">
          <RefreshCw className="w-4 h-4 animate-spin" />
          <span>Loading graph from Brigade...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        ref={containerRef}
        className="bg-rose-50 border border-rose-200 rounded-lg p-4"
      >
        <p className="text-sm text-rose-900 mb-3">
          Couldn't load Brigade graph: {error}
        </p>
        <button
          onClick={fetchGraph}
          className="px-3 py-1.5 bg-rose-600 text-white text-xs font-medium rounded-md hover:bg-rose-700 transition-colors inline-flex items-center gap-2"
        >
          <RefreshCw className="w-3 h-3" />
          Retry
        </button>
      </div>
    );
  }

  if (!data || data.reason === 'not_synced_yet' || data.nodes.length === 0) {
    const isNotSynced = !data || data.reason === 'not_synced_yet';
    return (
      <div
        ref={containerRef}
        className="bg-slate-50 border border-slate-200 rounded-lg p-6 text-sm text-slate-700"
      >
        {isNotSynced ? (
          <p>
            This meeting hasn't been synced to Brigade yet. Sync happens
            automatically when reprocess completes. (If Brigade isn't
            configured in production, you'll see this state for all
            meetings.)
          </p>
        ) : (
          <div>
            <p className="mb-3">
              Brigade is currently unreachable for the inline graph.
              {data?.graph_url ? ' You can still open the full graph in Brigade.' : ''}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={fetchGraph}
                className="px-3 py-1.5 bg-slate-700 text-white text-xs font-medium rounded-md hover:bg-slate-800 transition-colors inline-flex items-center gap-2"
              >
                <RefreshCw className="w-3 h-3" />
                Retry
              </button>
              {data?.graph_url && (
                <a
                  href={data.graph_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-3 py-1.5 bg-indigo-600 text-white text-xs font-medium rounded-md hover:bg-indigo-700 transition-colors inline-flex items-center gap-2"
                >
                  Open in Brigade
                  <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          </div>
        )}
      </div>
    );
  }

  // ------------------------------------------------------------------
  // 3D graph — rendered only when nodes are present.
  // ------------------------------------------------------------------
  return (
    <div ref={containerRef} className="space-y-3">
      <div
        className="bg-slate-900 rounded-lg overflow-hidden border border-slate-200 relative"
        style={{ height }}
      >
        {containerWidth > 0 && (
          <ForceGraph3D
            // react-force-graph-3d's ref typing is generic and depends
            // on the node/link generic params; we don't use the imperative
            // API today so a loose any-cast keeps the call-site type-clean
            // without dragging in ForceGraphMethods from the lib.
            ref={fgRef as React.MutableRefObject<any>}
            graphData={graphData}
            width={containerWidth}
            height={height}
            backgroundColor="#0f172a"
            nodeColor={(n: unknown) => colorForLabel((n as BrigadeNode).label)}
            nodeVal={(n: unknown) => sizeForNode(n as BrigadeNode)}
            nodeLabel={(n: unknown) => {
              const node = n as BrigadeNode;
              return showLabels ? `${node.label}: ${node.name}` : node.name;
            }}
            linkLabel={(l: unknown) => (l as BrigadeLink).type}
            linkColor={() => 'rgba(148, 163, 184, 0.6)'}
            linkWidth={1}
            linkDirectionalParticles={1}
            linkDirectionalParticleSpeed={0.005}
            onNodeClick={(n: unknown) => setSelectedNode(n as BrigadeNode)}
            onBackgroundClick={() => setSelectedNode(null)}
            enableNodeDrag={true}
            cooldownTicks={120}
          />
        )}
        {/* Legend */}
        <div className="absolute top-2 left-2 bg-slate-800/80 backdrop-blur rounded-md px-3 py-2 text-xs text-slate-100 space-y-1">
          <div className="font-semibold mb-1 text-slate-300">Legend</div>
          {Object.entries(LABEL_COLORS).map(([label, color]) => (
            <div key={label} className="flex items-center gap-2">
              <span
                className="inline-block w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: color }}
              />
              <span>{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Selected node detail panel — appears below the canvas when a
          node is clicked. Click background to dismiss. */}
      {selectedNode && (
        <div className="bg-white border border-slate-200 rounded-lg p-4 text-sm">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="flex items-center gap-2">
              <span
                className="inline-block w-3 h-3 rounded-full"
                style={{ backgroundColor: colorForLabel(selectedNode.label) }}
              />
              <span className="font-semibold text-slate-900">
                {selectedNode.label}
              </span>
              <span className="text-slate-500">{selectedNode.name}</span>
            </div>
            <button
              onClick={() => setSelectedNode(null)}
              className="text-slate-400 hover:text-slate-600 text-xs"
              aria-label="Close detail"
            >
              Close
            </button>
          </div>
          {selectedNode.properties &&
          Object.keys(selectedNode.properties).length > 0 ? (
            <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-xs text-slate-700">
              {Object.entries(selectedNode.properties).map(([k, v]) => (
                <React.Fragment key={k}>
                  <dt className="font-mono text-slate-500">{k}</dt>
                  <dd className="break-words text-slate-800">
                    {v === null || v === undefined ? (
                      <span className="text-slate-400 italic">null</span>
                    ) : typeof v === 'object' ? (
                      <code className="font-mono text-[11px]">
                        {JSON.stringify(v)}
                      </code>
                    ) : (
                      String(v)
                    )}
                  </dd>
                </React.Fragment>
              ))}
            </dl>
          ) : (
            <p className="text-xs text-slate-500 italic">
              No additional properties stored on this node.
            </p>
          )}
        </div>
      )}

      {/* "Open in Brigade" full-screen affordance */}
      {data.graph_url && (
        <div className="flex items-center justify-between gap-3 text-xs text-slate-600 px-1">
          <span>
            {data.nodes.length} node{data.nodes.length === 1 ? '' : 's'},{' '}
            {data.links.length} edge{data.links.length === 1 ? '' : 's'}
            {data.synced_at && (
              <>
                {' '}
                synced {new Date(data.synced_at).toLocaleString()}
              </>
            )}
          </span>
          <a
            href={data.graph_url}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 bg-indigo-600 text-white text-xs font-medium rounded-md hover:bg-indigo-700 transition-colors inline-flex items-center gap-2"
          >
            Open in Brigade
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      )}
    </div>
  );
};

export default BrigadeGraphViewer;
