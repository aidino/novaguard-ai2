// ckg_graph.js
// Handles fetching and rendering the Code Knowledge Graph (CKG) visualization

// Ensure Cytoscape.js is loaded in your HTML!

window.CKGGraph = {
    cy: null,
    config: {
        apiUrl: '/api/ckg/graph',
        containerId: 'project-graph-vis',
        defaultMode: 'architectural_overview',
        defaultDetailLevel: 1,
    },
    async fetchGraphData(params) {
        const url = new URL(this.config.apiUrl, window.location.origin);
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined && value !== null) {
                url.searchParams.append(key, value);
            }
        });
        const resp = await fetch(url);
        if (!resp.ok) throw new Error('Failed to fetch graph data');
        return await resp.json();
    },
    renderGraph(graphData) {
        if (!window.cytoscape) {
            document.getElementById(this.config.containerId).innerHTML = '<div style="color:red">Cytoscape.js not loaded</div>';
            return;
        }
        if (this.cy) this.cy.destroy();
        this.cy = cytoscape({
            container: document.getElementById(this.config.containerId),
            elements: this.transformData(graphData),
            style: [
                { selector: 'node[type="File"]', style: { 'background-color': '#6366f1', 'label': 'data(label)' } },
                { selector: 'node[type="Class"]', style: { 'background-color': '#38bdf8', 'label': 'data(label)' } },
                { selector: 'node[type="Function"]', style: { 'background-color': '#f59e0b', 'label': 'data(label)' } },
                { selector: 'node[?isProblematic]', style: { 'border-width': 4, 'border-color': '#ef4444' } },
                { selector: 'edge', style: { 'width': 2, 'line-color': '#bbb', 'target-arrow-color': '#bbb', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'label': 'data(label)' } },
            ],
            layout: { name: 'cose', animate: true },
        });
        // Add interactivity (zoom, pan, click, etc.)
        this.cy.on('tap', 'node', function(evt){
            const node = evt.target;
            // TODO: Show node details in sidebar or tooltip
            alert('Node: ' + node.data('label'));
        });
    },
    transformData(graphData) {
        // Convert backend nodes/edges to Cytoscape.js format
        const nodes = (graphData.nodes || []).map(n => ({
            data: {
                id: n.id,
                label: n.properties?.label || n.properties?.name || n.id,
                type: n.properties?.type || (n.labels ? n.labels[0] : undefined),
                ...n.properties,
                ...(graphData.highlight?.nodes?.[n.id] || {})
            }
        }));
        const edges = (graphData.edges || []).map(e => ({
            data: {
                id: e.id,
                source: e.source || e.from,
                target: e.target || e.to,
                label: e.properties?.label || e.type,
                ...e.properties,
                ...(graphData.highlight?.edges?.[e.id] || {})
            }
        }));
        return [...nodes, ...edges];
    },
    async init(params = {}) {
        const graphData = await this.fetchGraphData({
            mode: params.mode || this.config.defaultMode,
            detail_level: params.detail_level || this.config.defaultDetailLevel,
            project_graph_id: params.project_graph_id,
            changed_node_ids: params.changed_node_ids,
            central_node_id: params.central_node_id,
            context_node_ids: params.context_node_ids,
            depth: params.depth,
            filters: params.filters ? JSON.stringify(params.filters) : undefined,
        });
        this.renderGraph(graphData);
    }
}; 