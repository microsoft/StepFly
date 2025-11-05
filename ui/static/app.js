/**
 * StepFly Dashboard Frontend
 * Real-time monitoring and visualization of TSG execution
 */

// Global variables
let sessionId = null;
let autoUpdate = true;
let updateInterval = null;
let schedulerPollInterval = null;
let currentNodeStatus = [];
let currentEdgeStatus = [];
let currentPlanDAG = [];
let selectedNode = null;
let refreshRate = 1000; // 1 second default
let sessionActive = false;
let debugMode = true; // Enable debug logging

// New diagram controller instance
let diagramController = null;

// Initialize Mermaid
mermaid.initialize({
    startOnLoad: false,
    theme: 'default',
    themeVariables: {
        primaryColor: '#f9f9f9',
        primaryTextColor: '#333',
        primaryBorderColor: '#ccc',
        lineColor: '#333',
        secondaryColor: '#006100',
        tertiaryColor: '#fff'
    },
    flowchart: {
        htmlLabels: true,
        curve: 'basis'
    }
});

// Initialize application
document.addEventListener('DOMContentLoaded', function() {
    // Don't auto-start, wait for user to click "Start New Session"
    document.getElementById('sessionId').textContent = 'Not Started';
    
    // Show scheduler sidebar by default
    document.getElementById('schedulerSidebar').classList.add('active');
    
    // Initialize the new diagram controller
    diagramController = new DiagramController();
    diagramController.init('mermaidWrapper', 'mermaidDiagram');
    
    // Add keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Only handle shortcuts if not typing in an input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        
        if (e.key === '+' || e.key === '=') {
            e.preventDefault();
            diagramController?.zoomIn();
        } else if (e.key === '-' || e.key === '_') {
            e.preventDefault();
            diagramController?.zoomOut();
        } else if (e.key === '0') {
            e.preventDefault();
            diagramController?.resetZoom();
        }
    });
    
    // Debug info
    console.log('StepFly Dashboard UI Loaded');
    console.log('Mermaid version:', mermaid.version);
    console.log('Debug mode:', debugMode);
    console.log('Keyboard shortcuts: + (zoom in), - (zoom out), 0 (reset)');
    console.log('');
    console.log('🛠️ Debugging commands:');
    console.log('  showSimpleDiagram() - Show a test diagram');
    console.log('  forceRefreshDiagram() - Force refresh current diagram');
    console.log('  testMermaidDiagram() - Test with sample data');
    console.log('  testNodeClicking() - Test node click detection');
    console.log('  checkDiagramStatus() - Check current diagram status');
    console.log('  checkDiagramBounds() - Check if diagram is fully visible');
    console.log('  forceCenterDiagram() - Force center and fit diagram to viewport');
    console.log('  diagramController.getState() - View controller state');
    console.log('  diagramController.setState({scale: 1, translateX: 0, translateY: 0}) - Set state manually');
    console.log('  diagramController.clearSavedState() - Clear saved position');
    console.log('  diagramController.hasSavedState() - Check if position is saved');
});

// Start new session
async function startNewSession() {
    try {
        // Show loading
        document.getElementById('loadingOverlay').style.display = 'flex';
        document.getElementById('startSessionBtn').disabled = true;
        
        // Call API to start new session
        const response = await fetch('/api/session/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            sessionId = data.session_id;
            sessionActive = true;
            
            // Update UI
            document.getElementById('sessionId').textContent = sessionId;
            document.getElementById('startSessionBtn').textContent = '🔄 Restart Session';
            document.getElementById('startSessionBtn').disabled = false;
            
            // Clear scheduler conversation
            document.getElementById('schedulerConversation').innerHTML = '';
            
            // Start polling for scheduler messages
            startSchedulerPolling();
            
            // Start data fetching
            startDataFetching();
            
            showMessage('✅ Session started successfully!', 'success');
        } else {
            showMessage('Failed to start session: ' + data.error, 'error');
            document.getElementById('startSessionBtn').disabled = false;
        }
        
        // Hide loading
        setTimeout(() => {
            document.getElementById('loadingOverlay').style.display = 'none';
        }, 500);
        
    } catch (error) {
        console.error('Error starting session:', error);
        showMessage('Error starting session', 'error');
        document.getElementById('startSessionBtn').disabled = false;
        document.getElementById('loadingOverlay').style.display = 'none';
    }
}

// Start fetching data periodically
function startDataFetching() {
    if (!sessionActive) {
        console.log('Session not active, skipping data fetching');
        return;
    }
    
    console.log('Starting data fetching...');
    fetchData(); // Initial fetch
    
    if (updateInterval) {
        clearInterval(updateInterval);
    }
    
    updateInterval = setInterval(() => {
        if (autoUpdate && sessionActive) {
            fetchData();
        }
    }, refreshRate);
}

// Track if we're currently waiting for input
let currentlyWaitingForInput = false;

// Start polling scheduler conversation
function startSchedulerPolling() {
    if (schedulerPollInterval) {
        clearInterval(schedulerPollInterval);
    }
    
    // Poll every 500ms for scheduler messages
    schedulerPollInterval = setInterval(async () => {
        if (!sessionActive) return;
        
        try {
            const response = await fetch(`/api/session/${sessionId}/scheduler/conversation`);
            const data = await response.json();
            
            if (data.success) {
                updateSchedulerConversation(data.conversation);
                
                // Check if user input is needed
                if (data.waiting_for_input) {
                    if (!currentlyWaitingForInput) {
                        showUserInputSection(data.input_prompt);
                        currentlyWaitingForInput = true;
                    } else {
                        // Update prompt if it changes during polling and ensure input field is enabled
                        showUserInputSection(data.input_prompt);
                    }
                } else {
                    if (currentlyWaitingForInput) {
                        hideUserInputSection();
                        currentlyWaitingForInput = false;
                    } else {
                        // Ensure input field is not left disabled when not waiting for input
                        hideUserInputSection();
                    }
                }
            }
        } catch (error) {
            console.error('Error polling scheduler:', error);
        }
    }, 500);
}

// Track last conversation length to detect new messages
let lastConversationLength = 0;

// Update scheduler conversation display
function updateSchedulerConversation(conversation) {
    const container = document.getElementById('schedulerConversation');
    
    // Only update if there are new messages
    if (conversation.length === 0) return;
    
    // Check if we have new messages
    if (conversation.length === lastConversationLength) {
        return; // No new messages, don't rebuild
    }
    
    // Only append new messages instead of rebuilding everything
    const newMessages = conversation.slice(lastConversationLength);
    
    // If this is the first update or we need to rebuild
    if (lastConversationLength === 0) {
        container.innerHTML = '';
        conversation.forEach(msg => {
            appendSchedulerMessage(container, msg);
        });
    } else {
        // Just append the new messages
        newMessages.forEach(msg => {
            appendSchedulerMessage(container, msg);
        });
    }
    
    // Update last conversation length
    lastConversationLength = conversation.length;
    
    // If the latest message is a question/requires input, ensure input area is available
    const lastMsg = conversation[conversation.length - 1];
    if (lastMsg && typeof lastMsg.content === 'string') {
        const needsInputCue = /please\s+provide|need\s+to\s+ask|select\s+and\s+load|enter\s+your\s+response/i.test(lastMsg.content);
        if (needsInputCue) {
            showUserInputSection(document.getElementById('inputPrompt').textContent || '');
        }
    }
    
    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

// Helper function to append a single message
function appendSchedulerMessage(container, msg) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `scheduler-msg ${msg.role}`;
    if (msg.role === 'system') {
        msgDiv.innerHTML = `
            <span class="msg-time">${new Date(msg.timestamp).toLocaleTimeString()}</span>
            <span class="msg-content system">💻 ${escapeHtml(msg.content)}</span>
        `;
    } else if (msg.role === 'scheduler') {
        const icon = msg.style === 'green' ? '✅' : 
                     msg.style === 'red' ? '❌' : 
                     msg.style === 'yellow' ? '⚠️' : '🤖';
        msgDiv.innerHTML = `
            <span class="msg-time">${new Date(msg.timestamp).toLocaleTimeString()}</span>
            <span class="msg-content scheduler">${icon} ${escapeHtml(msg.content)}</span>
        `;
    } else if (msg.role === 'tool') {
        msgDiv.innerHTML = `
            <span class="msg-time">${new Date(msg.timestamp).toLocaleTimeString()}</span>
            <span class="msg-content tool">🔧 ${escapeHtml(msg.content)}</span>
        `;
    } else if (msg.role === 'user') {
        msgDiv.innerHTML = `
            <span class="msg-time">${new Date(msg.timestamp).toLocaleTimeString()}</span>
            <span class="msg-content user">👤 ${escapeHtml(msg.content)}</span>
        `;
    } else if (msg.role === 'error') {
        msgDiv.innerHTML = `
            <span class="msg-time">${new Date(msg.timestamp).toLocaleTimeString()}</span>
            <span class="msg-content error">❌ ${escapeHtml(msg.content)}</span>
        `;
    }
    
    container.appendChild(msgDiv);
}

// Show user input section
function showUserInputSection(prompt) {
    const section = document.getElementById('userInputSection');
    const promptDiv = document.getElementById('inputPrompt');
    const inputField = document.getElementById('userInputField');
    const sendButton = document.querySelector('.input-container button');
    
    // Ensure section is visible and prompt is up-to-date
    if (section.style.display === 'none') {
        section.style.display = 'block';
    }
    if (promptDiv.textContent !== prompt) {
        promptDiv.textContent = prompt;
    }

    // Always re-enable input and button when (re)showing the prompt
    if (inputField.disabled) inputField.disabled = false;
    if (sendButton && sendButton.disabled) sendButton.disabled = false;

    // Focus the input to allow immediate typing
    // If there is existing text (user might want to modify previous input), select it for quick replacement
    setTimeout(() => {
        inputField.focus();
        if (inputField.value && inputField.value.length > 0) {
            inputField.select();
        }
    }, 0);
}

// Hide user input section
function hideUserInputSection() {
    const section = document.getElementById('userInputSection');
    const inputField = document.getElementById('userInputField');
    const sendButton = document.querySelector('.input-container button');
    section.style.display = 'none';
    // Prevent residual disabled state from affecting next input
    if (inputField.disabled) inputField.disabled = false;
    if (sendButton && sendButton.disabled) sendButton.disabled = false;
}

// Send user input
async function sendUserInput() {
    const inputField = document.getElementById('userInputField');
    const sendButton = document.querySelector('.input-container button');
    const userInput = inputField.value.trim();
    
    if (!userInput) {
        showMessage('Please enter a response', 'warning');
        return;
    }
    
    try {
        // Disable input while sending
        inputField.disabled = true;
        if (sendButton) sendButton.disabled = true;
        
        const response = await fetch(`/api/session/${sessionId}/user-input`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input: userInput })
        });
        
        const data = await response.json();
        
        if (data.success) {
            inputField.value = '';
            // Let polling switch UI based on backend waiting_for_input, but to prevent hanging, reset locally and temporarily enable input field
            currentlyWaitingForInput = false;
            inputField.disabled = false;
            if (sendButton) sendButton.disabled = false;
            // Do not immediately hide input area, wait for polling confirmation
        } else {
            showMessage('Failed to send input: ' + data.error, 'error');
            // Re-enable input on error
            inputField.disabled = false;
            if (sendButton) sendButton.disabled = false;
        }
    } catch (error) {
        console.error('Error sending user input:', error);
        showMessage('Error sending input', 'error');
        // Re-enable input on error
        inputField.disabled = false;
        if (sendButton) sendButton.disabled = false;
    }
}

// Handle enter key in input field
function handleUserInputKeypress(event) {
    if (event.key === 'Enter') {
        sendUserInput();
    }
}

// Toggle scheduler sidebar
function toggleSchedulerSidebar() {
    const sidebar = document.getElementById('schedulerSidebar');
    const willMinimize = !sidebar.classList.contains('minimized');
    sidebar.classList.toggle('minimized');
    const btn = sidebar.querySelector('.minimize-btn');
    if (!willMinimize) {
        // When expanding, ensure it becomes active width immediately
        sidebar.classList.add('active');
        // Focus the conversation container for scroll
        const conv = document.getElementById('schedulerConversation');
        if (conv) conv.scrollTop = conv.scrollHeight;
        if (btn) btn.title = 'Collapse';
    } else {
        // When minimizing, keep it active so header/button is visible
        sidebar.classList.add('active');
        if (btn) btn.title = 'Expand';
    }
}

// Fetch data from API
async function fetchData() {
    if (!sessionId || !sessionActive) {
        console.log('Skipping fetch: no session or inactive');
        return;
    }
    
    try {
        console.log('Fetching data for session:', sessionId);
        const response = await fetch(`/api/session/${sessionId}/status`);
        const data = await response.json();
        
        if (data.success) {
            console.log('Data received, updating visualization...');
            await updateVisualization(data);
            updateStatistics(data.statistics);
            updateConnectionStatus(true);
            updateLastUpdateTime();
        } else {
            console.error('Failed to fetch data:', data.error);
            showMessage('Failed to fetch data: ' + data.error, 'error');
            updateConnectionStatus(false);
        }
    } catch (error) {
        console.error('Error fetching data:', error);
        updateConnectionStatus(false);
    }
}

// Update the visualization
async function updateVisualization(data) {
    console.log('updateVisualization called with:', {
        node_count: data.node_status ? data.node_status.length : 0,
        edge_count: data.edge_status ? data.edge_status.length : 0,
        plandag_count: data.plandag_nodes ? data.plandag_nodes.length : 0
    });
    
    currentNodeStatus = data.node_status || [];
    currentEdgeStatus = data.edge_status || [];
    currentPlanDAG = data.plandag_nodes || [];
    
    // If no nodes yet, show waiting message
    if (currentNodeStatus.length === 0) {
        console.log('No nodes found, showing waiting message');
        const element = document.getElementById('mermaidDiagram');
        element.innerHTML = '<div style="text-align: center; padding: 2rem; color: #666;">Waiting for TSG to load...</div>';
        return;
    }
    
    console.log('Processing', currentNodeStatus.length, 'nodes');
    
    try {
        // Get edge connections
        const edgeResponse = await fetch(`/api/session/${sessionId}/edges`);
        const edgeData = await edgeResponse.json();
        const connections = edgeData.connections || [];
        
        // Generate Mermaid diagram
        const mermaidCode = generateMermaidDiagram(currentNodeStatus, connections);
        
        // Debug: Log the generated code
        console.log('Generated Mermaid code:', mermaidCode);
        
        // Update the diagram
        const element = document.getElementById('mermaidDiagram');
        
        // Clear previous content
        element.innerHTML = '';
        
        // Create a new div with mermaid class
        const wrapper = document.createElement('div');
        wrapper.className = 'mermaid';
        wrapper.textContent = mermaidCode;
        wrapper.style.minWidth = '800px';
        wrapper.style.minHeight = '600px';
        
        element.appendChild(wrapper);
        
        // Render with Mermaid
        try {
            console.log('Attempting to render Mermaid diagram...');
            await mermaid.run();
            console.log('Mermaid diagram rendered successfully');
            
            // After Mermaid renders, use the new controller to position
            const svgElement = element.querySelector('svg');
            if (svgElement) {
                svgElement.style.display = 'block';
                svgElement.style.margin = '0';
                
                // Use the new diagram controller for positioning
                if (diagramController && diagramController.state.initialized) {
                    // Give Mermaid time to fully stabilize the SVG
                    setTimeout(() => {
                        // Check if there's a saved state to restore
                        if (diagramController.hasSavedState()) {
                            console.log('Restoring saved diagram position...');
                            // The state has already been loaded in init(), just need to reapply
                            diagramController.applyTransform(false);
                        } else {
                            console.log('No saved state, fitting diagram to viewport...');
                            diagramController.fitToViewport();
                        }
                    }, 100); // Shorter delay since new controller is more reliable
                }
            }
        } catch (mermaidError) {
            console.error('Mermaid rendering error:', mermaidError);
            
            if (debugMode) {
                console.error('Problematic diagram:', mermaidCode);
                // Show error with the diagram code in debug mode
                element.innerHTML = `
                    <div style="padding: 1rem;">
                        <div style="color: red; margin-bottom: 1rem;">Mermaid Syntax Error</div>
                        <div style="margin-bottom: 1rem;">Check browser console for details</div>
                    </div>
                `;
            }
            
            // Try a very simple fallback diagram
            try {
                const simpleDiagram = generateSimpleFallbackDiagram(currentNodeStatus);
                const simpleWrapper = document.createElement('div');
                simpleWrapper.className = 'mermaid';
                simpleWrapper.textContent = simpleDiagram;
                element.innerHTML = '';
                element.appendChild(simpleWrapper);
                await mermaid.run();
                console.log('Fallback diagram rendered');
            } catch (fallbackError) {
                console.error('Fallback also failed:', fallbackError);
                // Show text-based status
                element.innerHTML = generateTextStatusDisplay(currentNodeStatus);
            }
        }
        
        // Add click handlers to nodes after rendering
        setTimeout(() => {
            addNodeClickHandlers();
            
            // Also try to bind handlers after a longer delay for complex diagrams
            setTimeout(() => {
                addNodeClickHandlers();
            }, 1500);
        }, 800);
    } catch (error) {
        console.error('Error updating visualization:', error);
        // Show a fallback message
        const element = document.getElementById('mermaidDiagram');
        element.innerHTML = '<div style="text-align: center; padding: 2rem; color: #666;">Error rendering diagram. Check console for details.</div>';
    }
}

// Generate valid Mermaid node ID (alphanumeric only)
function getMermaidNodeId(nodeId) {
    // Keep alphanumeric and underscore, replace others
    return 'node_' + nodeId.replace(/[^a-zA-Z0-9]/g, '_');
}

// Escape text for Mermaid labels - minimal escaping
function escapeMermaidLabel(text) {
    if (!text) return '';
    // Basic HTML escaping for labels
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, "'")
        .replace(/\n/g, ' ')
        .replace(/\r/g, '')
        .trim();
}

// Generate Mermaid diagram code with better syntax
function generateMermaidDiagram(nodeStatus, connections) {
    let diagram = 'graph TD\n';
    
    // Create node ID mapping
    const nodeMap = {};
    nodeStatus.forEach(node => {
        nodeMap[node.node] = getMermaidNodeId(node.node);
    });
    
    // Add nodes
    nodeStatus.forEach(node => {
        const mermaidId = nodeMap[node.node];
        const label = escapeMermaidLabel(node.node);
        const status = node.status || 'pending';
        
        // Simple node shapes without complex HTML
        if (node.node.toLowerCase() === 'start' || node.node.toLowerCase() === 'end') {
            diagram += `    ${mermaidId}(${label})\n`;
        } else {
            diagram += `    ${mermaidId}[${label}]\n`;
        }
        
        // Apply style class
        diagram += `    ${mermaidId}:::${status}\n`;
    });
    
    diagram += '\n';
    
    // Add edges with consistent arrow style
    const linkStyles = []; // Track edge styles for coloring
    let linkIndex = 0;
    
    connections.forEach(conn => {
        const sourceId = nodeMap[conn.source];
        const targetId = nodeMap[conn.target];
        
        if (!sourceId || !targetId) {
            console.warn('Missing node mapping for edge:', conn);
            return;
        }
        
        // Use standard arrows for all edges, distinguish by color instead
        let edgeLine = '';
        const status = conn.status || 'pending';
        
        if (conn.condition && conn.condition !== 'none') {
            const label = escapeMermaidLabel(conn.condition);
            const shortLabel = label.length > 20 ? label.substring(0, 17) + '...' : label;
            edgeLine = `    ${sourceId} -->|${shortLabel}| ${targetId}\n`;
        } else {
            edgeLine = `    ${sourceId} --> ${targetId}\n`;
        }
        
        diagram += edgeLine;
        
        // Record link style for coloring
        linkStyles.push({
            index: linkIndex,
            status: status
        });
        linkIndex++;
    });
    
    // Add style definitions at the end
    diagram += '\n';
    diagram += '    classDef pending fill:#6c757d,stroke:#333,stroke-width:2px,color:#fff\n';
    diagram += '    classDef running fill:#ffc107,stroke:#333,stroke-width:3px,color:#000\n';
    diagram += '    classDef finished fill:#28a745,stroke:#333,stroke-width:2px,color:#fff\n';
    diagram += '    classDef failed fill:#dc3545,stroke:#333,stroke-width:2px,color:#fff\n';
    diagram += '    classDef skipped fill:#17a2b8,stroke:#333,stroke-width:2px,color:#fff\n';
    
    // Add edge color styles based on status
    diagram += '\n';
    linkStyles.forEach(link => {
        const color = getEdgeColor(link.status);
        diagram += `    linkStyle ${link.index} stroke:${color},stroke-width:3px\n`;
    });
    
    return diagram;
}

// Get edge color based on status  
function getEdgeColor(status) {
    switch(status) {
        case 'enabled':
            return '#28a745'; // Green
        case 'disabled':
            return '#dc3545'; // Red
        case 'pending':
            return '#6c757d'; // Gray
        default:
            return '#6c757d'; // Default to gray
    }
}

// Get edge style based on status (deprecated - kept for compatibility)
function getEdgeStyle(status) {
    const color = getEdgeColor(status);
    return `stroke:${color},stroke-width:3px`;
}

// Add click handlers to nodes
function addNodeClickHandlers() {
    console.log('Adding click handlers to nodes...');
    
    currentNodeStatus.forEach(node => {
        const mermaidId = getMermaidNodeId(node.node);
        
        // Find all g elements that might contain our node
        const allGroups = document.querySelectorAll('g');
        
        allGroups.forEach(g => {
            // Check if this group contains text matching our node
            const textElements = g.querySelectorAll('text');
            const rectElements = g.querySelectorAll('rect');
            let isOurNode = false;
            
            // Check text content
            textElements.forEach(text => {
                if (text.textContent && (
                    text.textContent.includes(node.node) ||
                    text.textContent === node.node
                )) {
                    isOurNode = true;
                }
            });
            
            // Also check the group's ID
            if (g.id && (g.id.includes(mermaidId) || g.id.includes(node.node))) {
                isOurNode = true;
            }
            
            // Check if there's a rect (node background) and text
            if (!isOurNode && rectElements.length > 0 && textElements.length > 0) {
                // This might be a node group, check the text
                const groupText = g.textContent || '';
                if (groupText.includes(node.node)) {
                    isOurNode = true;
                }
            }
            
            if (isOurNode) {
                console.log(`Found node element for ${node.node}:`, g);
                
                // Make the entire group clickable
                g.style.cursor = 'pointer';
                g.setAttribute('data-node-id', node.node);
                
                // Add click handler
                g.onclick = function(e) {
                    e.stopPropagation();
                    console.log('Node clicked:', node.node);
                    loadNodeDetails(node.node);
                };
                
                // Also make child elements clickable
                const children = g.querySelectorAll('*');
                children.forEach(child => {
                    child.style.cursor = 'pointer';
                    child.onclick = function(e) {
                        e.stopPropagation();
                        console.log('Node child clicked:', node.node);
                        loadNodeDetails(node.node);
                    };
                });
                
                // Add hover effect
                g.onmouseover = function() {
                    this.style.opacity = '0.7';
                };
                g.onmouseout = function() {
                    this.style.opacity = '1';
                };
            }
        });
    });
    
    console.log('Finished adding click handlers');
}

// Load node details when clicked
async function loadNodeDetails(nodeId) {
    console.log('Loading details for node:', nodeId);
    
    // Remove previous selection highlighting
    document.querySelectorAll('g.selected-node').forEach(g => {
        g.classList.remove('selected-node');
    });
    
    // Add selection highlighting to clicked node
    document.querySelectorAll('g[data-node-id]').forEach(g => {
        if (g.getAttribute('data-node-id') === nodeId) {
            g.classList.add('selected-node');
        }
    });
    
    selectedNode = nodeId;
    
    // Show sidebar
    document.getElementById('sidebar').classList.add('active');
    
    // Update node info
    const node = currentNodeStatus.find(n => n.node === nodeId);
    if (node) {
        document.getElementById('nodeName').textContent = nodeId;
        document.getElementById('nodeDescription').textContent = node.description || 'No description';
        
        const statusBadge = document.getElementById('nodeStatusBadge');
        statusBadge.textContent = node.status || 'pending';
        statusBadge.className = `node-status-badge ${node.status}`;
        
        document.getElementById('executorId').textContent = node.executor_id || '-';
    }
    
    // Load conversation history
    try {
        const response = await fetch(`/api/session/${sessionId}/node/${nodeId}/conversation`);
        const data = await response.json();
        
        if (data.success && data.conversation && data.conversation.length > 0) {
            displayConversation(data.conversation);
            
            // Display execution result if available
            if (data.node_info && data.node_info.result) {
                displayExecutionResult(data.node_info.result);
            }
        } else {
            showNoConversation();
        }
    } catch (error) {
        console.error('Error loading node conversation:', error);
        showNoConversation();
    }
}

// Display conversation history
function displayConversation(conversation) {
    const container = document.getElementById('conversationHistory');
    const noConvDiv = document.getElementById('noConversation');
    
    container.innerHTML = '';
    container.style.display = 'block';
    noConvDiv.style.display = 'none';
    
    conversation.forEach((msg, index) => {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${msg.role} collapsible`;
        
        const headerClass = msg.role === 'system' ? 'system'
                            : msg.role === 'user' ? 'user'
                            : 'assistant';

        // Build collapsible message with toggle button
        const isSystem = msg.role === 'system';
        const defaultCollapsed = isSystem; // System messages are collapsed by default; others are expanded
        const initialDisplay = defaultCollapsed ? 'none' : 'block';
        const initialBtnText = defaultCollapsed ? 'Show' : 'Hide';

        let bodyHtml = '';
        if (msg.role === 'assistant' && msg.parsed) {
            bodyHtml = `${formatAssistantMessage(msg.parsed)}`;
        } else {
            bodyHtml = `<pre>${escapeHtml(msg.content)}</pre>`;
        }

        messageDiv.innerHTML = `
            <div class="message-header ${headerClass}">
                <span class="role-label">${msg.role === 'system' ? '🖥️ System' : (msg.role === 'user' ? '👤 User/Observation' : '🤖 AI Assistant')}</span>
                <button class="expand-btn" onclick="toggleMessage(${index})">${initialBtnText}</button>
            </div>
            <div class="message-content" id="msg-${index}" style="display: ${initialDisplay};">
                ${bodyHtml}
            </div>
        `;
        
        container.appendChild(messageDiv);
    });
}

// Format assistant message
function formatAssistantMessage(parsed) {
    let html = '<div class="assistant-parsed">';
    
    if (parsed.thought) {
        html += `
            <div class="thought-section">
                <strong>💭 Thought:</strong>
                <p>${escapeHtml(parsed.thought)}</p>
            </div>
        `;
    }
    
    if (parsed.action) {
        html += `
            <div class="action-section">
                <strong>⚡ Action:</strong>
                <span class="action-name">${escapeHtml(parsed.action)}</span>
            </div>
        `;
    }
    
    if (parsed.parameters && Object.keys(parsed.parameters).length > 0) {
        html += `
            <div class="parameters-section">
                <strong>📋 Parameters:</strong>
                <pre class="parameters">${JSON.stringify(parsed.parameters, null, 2)}</pre>
            </div>
        `;
    }
    
    html += '</div>';
    return html;
}

// Display execution result
function displayExecutionResult(result) {
    const resultSection = document.getElementById('resultSection');
    const resultContent = document.getElementById('resultContent');
    
    try {
        const resultData = typeof result === 'string' ? JSON.parse(result) : result;
        
        let html = '<div class="result-data">';
        
        if (resultData.result) {
            html += `<div class="result-text"><strong>Result:</strong> ${escapeHtml(resultData.result)}</div>`;
        }
        
        if (resultData.set_edge_status) {
            html += '<div class="edge-updates"><strong>Edge Updates:</strong><ul>';
            for (const [edge, status] of Object.entries(resultData.set_edge_status)) {
                html += `<li>${edge}: <span class="edge-status ${status}">${status}</span></li>`;
            }
            html += '</ul></div>';
        }
        
        html += '</div>';
        
        resultContent.innerHTML = html;
        resultSection.style.display = 'block';
    } catch (e) {
        console.error('Error parsing result:', e);
        resultSection.style.display = 'none';
    }
}

// Show no conversation message
function showNoConversation() {
    document.getElementById('conversationHistory').style.display = 'none';
    document.getElementById('noConversation').style.display = 'block';
    document.getElementById('resultSection').style.display = 'none';
}

// Update statistics
function updateStatistics(stats) {
    if (stats) {
        document.getElementById('totalNodes').textContent = stats.total_nodes || 0;
        document.getElementById('pendingNodes').textContent = stats.pending || 0;
        document.getElementById('runningNodes').textContent = stats.running || 0;
        document.getElementById('finishedNodes').textContent = stats.finished || 0;
        document.getElementById('failedNodes').textContent = stats.failed || 0;
        document.getElementById('skippedNodes').textContent = stats.skipped || 0;
    }
}

// Update connection status
function updateConnectionStatus(connected) {
    const statusElement = document.getElementById('connectionStatus');
    if (connected) {
        statusElement.innerHTML = '<span class="status-dot connected"></span> Connected';
    } else {
        statusElement.innerHTML = '<span class="status-dot disconnected"></span> Disconnected';
    }
}

// Update last update time
function updateLastUpdateTime() {
    const now = new Date();
    const timeString = now.toLocaleTimeString();
    document.getElementById('lastUpdate').textContent = timeString;
}

// Toggle auto-update
function toggleAutoUpdate() {
    autoUpdate = !autoUpdate;
    const btn = document.getElementById('autoUpdateBtn');
    btn.textContent = autoUpdate ? 'Pause Updates' : 'Resume Updates';
}

// Update refresh rate
function updateRefreshRate() {
    const select = document.getElementById('refreshRate');
    const newRate = parseInt(select.value);
    
    // Only restart if the rate actually changed
    if (newRate !== refreshRate) {
        refreshRate = newRate;
        console.log('Refresh rate changed to:', refreshRate, 'ms');
        
        // Clear and restart the interval with new rate
        if (updateInterval) {
            clearInterval(updateInterval);
        }
        
        if (sessionActive && autoUpdate) {
            updateInterval = setInterval(() => {
                if (autoUpdate && sessionActive) {
                    fetchData();
                }
            }, refreshRate);
        }
    }
}

// Setup zoom and pan controls
function setupZoomControls() {
    const wrapper = document.getElementById('mermaidWrapper');
    const container = document.getElementById('graphContainer');
    
    if (!wrapper || !container) {
        console.error('Zoom controls: wrapper or container not found');
        return;
    }
    
    // Mouse wheel zoom
    container.addEventListener('wheel', (e) => {
        e.preventDefault();
        const delta = e.deltaY * -0.001;
        const newScale = Math.min(Math.max(0.3, currentScale + delta), 3);
        
        currentScale = newScale;
        userInteracted = true;  // Stick to user's zoom level on updates
        updateTransform();
    });
    
    // Pan with mouse drag
    let isPanning = false;
    let startX = 0;
    let startY = 0;
    
    container.addEventListener('mousedown', (e) => {
        // Don't start panning if clicking on a node
        const isNode = e.target.closest('g[data-node-id]') || 
                      e.target.tagName === 'text' ||
                      e.target.tagName === 'rect' ||
                      e.target.tagName === 'path';
        
        if (e.button === 0 && !isNode) {
            isPanning = true;
            startX = e.clientX - translateX;
            startY = e.clientY - translateY;
            container.style.cursor = 'grabbing';
            userInteracted = true;  // Stick to user's pan position on updates
        }
    });
    
    window.addEventListener('mousemove', (e) => {
        if (isPanning) {
            translateX = e.clientX - startX;
            translateY = e.clientY - startY;
            updateTransform();
        }
    });
    
    window.addEventListener('mouseup', () => {
        if (isPanning) {
            isPanning = false;
            container.style.cursor = 'grab';
        }
    });
}

// Update transform for zoom and pan
function updateTransform() {
    const diagram = document.getElementById('mermaidDiagram');
    if (diagram) {
        const transformValue = `translate(${translateX}px, ${translateY}px) scale(${currentScale})`;
        diagram.style.transform = transformValue;
        diagram.style.transformOrigin = '0 0'; // CRITICAL: Use top-left origin for predictable behavior
        console.log(`Applied transform: ${transformValue}`);
    } else {
        console.warn('updateTransform: diagram element not found');
    }
}

// Simple, reliable fit function
function fitDiagramToViewportSimple() {
    console.log('=== fitDiagramToViewportSimple ===');
    
    const wrapper = document.getElementById('mermaidWrapper');
    const diagram = document.getElementById('mermaidDiagram');
    
    if (!wrapper || !diagram) {
        console.error('Missing wrapper or diagram');
        return;
    }
    
    const svg = diagram.querySelector('svg');
    if (!svg) {
        console.error('No SVG found');
        return;
    }
    
    // Get container dimensions
    const containerWidth = wrapper.clientWidth;
    const containerHeight = wrapper.clientHeight;
    console.log(`Container: ${containerWidth} x ${containerHeight}`);
    
    // Get SVG actual rendered size (not viewBox)
    const svgRect = svg.getBoundingClientRect();
    const diagramRect = diagram.getBoundingClientRect();
    
    console.log('SVG rect:', svgRect);
    console.log('Diagram rect:', diagramRect);
    
    // Calculate the actual content size
    const contentWidth = svg.scrollWidth || svgRect.width;
    const contentHeight = svg.scrollHeight || svgRect.height;
    console.log(`Content: ${contentWidth} x ${contentHeight}`);
    
    // Calculate scale to fit with padding
    const padding = 40;
    const scaleX = (containerWidth - padding * 2) / contentWidth;
    const scaleY = (containerHeight - padding * 2) / contentHeight;
    const scale = Math.min(scaleX, scaleY, 1); // Don't scale up, only down if needed
    
    console.log(`Scale calculation: X=${scaleX}, Y=${scaleY}, Final=${scale}`);
    
    // Calculate centered position
    const scaledWidth = contentWidth * scale;
    const scaledHeight = contentHeight * scale;
    const translateX = (containerWidth - scaledWidth) / 2;
    const translateY = (containerHeight - scaledHeight) / 2;
    
    console.log(`Position: translate(${translateX}, ${translateY}), scale(${scale})`);
    
    // Apply transform
    currentScale = scale;
    window.translateX = translateX;
    window.translateY = translateY;
    
    // Set transform with top-left origin
    diagram.style.transformOrigin = '0 0';
    diagram.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
    
    console.log('Transform applied successfully');
}

// Compute a best-fit transform so the whole SVG fits inside the wrapper
function fitDiagramToViewport(padding = 40) {
    const wrapper = document.getElementById('mermaidWrapper');
    const diagram = document.getElementById('mermaidDiagram');
    if (!wrapper || !diagram) {
        console.warn('fitDiagramToViewport: wrapper or diagram not found');
        return;
    }
    const svg = diagram.querySelector('svg');
    if (!svg) {
        console.warn('fitDiagramToViewport: SVG not found');
        return;
    }

    const cw = wrapper.clientWidth;
    const ch = wrapper.clientHeight;
    console.log(`Container size: ${cw} x ${ch}`);
    
    if (cw <= 0 || ch <= 0) {
        console.warn('fitDiagramToViewport: Invalid container size');
        return;
    }

    // Clear any existing transform first to get original dimensions
    diagram.style.transform = '';
    
    // Wait a frame for the transform clear to take effect
    requestAnimationFrame(() => {
        try {
            // Get the actual bounding box of all SVG content
            const bbox = svg.getBBox();
            console.log(`SVG BBox: x=${bbox.x}, y=${bbox.y}, width=${bbox.width}, height=${bbox.height}`);
            
            if (bbox.width <= 0 || bbox.height <= 0) {
                console.warn('fitDiagramToViewport: Invalid SVG bbox');
                return;
            }
            
            // Calculate scale to fit both width and height with padding
            const availableWidth = cw - padding * 2;
            const availableHeight = ch - padding * 2;
            
            const scaleX = availableWidth / bbox.width;
            const scaleY = availableHeight / bbox.height;
            const scale = Math.min(Math.max(0.1, Math.min(scaleX, scaleY)), 3);
            
            console.log(`Scale calculation: availableSize=${availableWidth}x${availableHeight}, scaleX=${scaleX}, scaleY=${scaleY}, finalScale=${scale}`);
            
            // Calculate translation to center the scaled content
            // We need to account for the bbox offset and scale
            const scaledWidth = bbox.width * scale;
            const scaledHeight = bbox.height * scale;
            const scaledOffsetX = bbox.x * scale;
            const scaledOffsetY = bbox.y * scale;
            
            // Center in container and adjust for bbox offset
            const centerX = (cw - scaledWidth) / 2;
            const centerY = (ch - scaledHeight) / 2;
            
            currentScale = scale;
            translateX = Math.round(centerX - scaledOffsetX);
            translateY = Math.round(centerY - scaledOffsetY);
            
            console.log(`Final positioning: scale=${scale}, translate=(${translateX}, ${translateY})`);
            console.log(`Scaled content: ${scaledWidth}x${scaledHeight}, offset=(${scaledOffsetX}, ${scaledOffsetY})`);
            
            updateTransform();
            
        } catch (e) {
            console.error('Error in fitDiagramToViewport:', e);
            // Fallback to simple center positioning
            currentScale = 1;
            translateX = 0;
            translateY = 0;
            updateTransform();
        }
    });
}

// Reset zoom - uses new controller
function resetZoom() {
    if (diagramController) {
        console.log('Resetting zoom with controller...');
        diagramController.fitToViewport();
    } else {
        console.log('Controller not initialized');
    }
}

// Zoom in - uses new controller
function zoomIn() {
    if (diagramController) {
        diagramController.zoomIn();
    }
}

// Zoom out - uses new controller
function zoomOut() {
    if (diagramController) {
        diagramController.zoomOut();
    }
}

// Clear saved position
function clearSavedPosition() {
    if (diagramController) {
        diagramController.clearSavedState();
        console.log('Saved position cleared');
        // Optionally, fit to viewport after clearing
        diagramController.fitToViewport();
        showMessage('Saved position cleared', 'info');
    }
}

// Window resize is now handled by DiagramController

// Close sidebar
function closeSidebar() {
    document.getElementById('sidebar').classList.remove('active');
    selectedNode = null;
}

// Toggle message visibility
function toggleMessage(index) {
    const msgContent = document.getElementById(`msg-${index}`);
    const isVisible = msgContent.style.display !== 'none';
    msgContent.style.display = isVisible ? 'none' : 'block';
    event.target.textContent = isVisible ? 'Show' : 'Hide';
}

// Toggle section (Conversation/Result)
function toggleSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (!section) return;
    const isConversation = sectionId === 'conversationSection';
    const content = section.querySelector(isConversation ? '.conversation-container' : '.result-content');
    const btn = section.querySelector('.section-toggle');
    if (!content || !btn) return;
    
    const isCurrentlyHidden = content.style.display === 'none' || section.classList.contains('collapsed');
    
    if (isCurrentlyHidden) {
        // Expanding
        content.style.display = 'block';
        section.classList.remove('collapsed');
        btn.textContent = '−';
    } else {
        // Collapsing  
        content.style.display = 'none';
        section.classList.add('collapsed');
        btn.textContent = '+';
    }
    
    // Force layout recalculation
    section.offsetHeight;
}

// Show message
function showMessage(text, type = 'info') {
    const container = document.getElementById('messageContainer');
    const content = document.getElementById('messageContent');
    
    content.textContent = text;
    content.className = `message-content ${type}`;
    container.style.display = 'block';
    
    // Different timeouts for different types
    const timeout = type === 'success' ? 3000 : 
                   type === 'warning' ? 4000 : 5000;
    
    setTimeout(() => {
        container.style.display = 'none';
    }, timeout);
}

// Close message
function closeMessage() {
    document.getElementById('messageContainer').style.display = 'none';
}

// Escape HTML for safe display
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// Generate simple fallback diagram without complex features
function generateSimpleFallbackDiagram(nodeStatus) {
    let diagram = 'graph TD\n';
    
    // Just show nodes without styling or complex edges
    nodeStatus.forEach((node, index) => {
        const nodeId = 'N' + index;
        const label = node.node + ' [' + (node.status || 'pending') + ']';
        diagram += `    ${nodeId}[${label}]\n`;
    });
    
    // Add simple linear connections
    for (let i = 0; i < nodeStatus.length - 1; i++) {
        diagram += `    N${i} --> N${i+1}\n`;
    }
    
    return diagram;
}

// Generate text-based status display as last resort
function generateTextStatusDisplay(nodeStatus) {
    let html = '<div style="padding: 2rem; font-family: monospace;">';
    html += '<h3>Execution Status</h3>';
    html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">';
    
    nodeStatus.forEach(node => {
        const statusColor = {
            'pending': '#6c757d',
            'running': '#ffc107',
            'finished': '#28a745',
            'failed': '#dc3545',
            'skipped': '#17a2b8'
        }[node.status] || '#6c757d';
        
        html += `
            <div style="border: 1px solid ${statusColor}; padding: 0.5rem; border-radius: 4px;">
                <div style="font-weight: bold; color: ${statusColor};">${node.node}</div>
                <div style="font-size: 0.85rem; color: #666;">${node.status || 'pending'}</div>
            </div>
        `;
    });
    
    html += '</div></div>';
    return html;
}

// Force refresh the diagram
window.forceRefreshDiagram = async function() {
    console.log('Force refreshing diagram...');
    try {
        // Fetch latest data
        const response = await fetch(`/api/session/${sessionId}/status`);
        const data = await response.json();
        
        if (data.success) {
            console.log('Data fetched:', data);
            await updateVisualization(data);
            console.log('Diagram refresh complete');
        } else {
            console.error('Failed to fetch data:', data.error);
        }
    } catch (error) {
        console.error('Error refreshing diagram:', error);
    }
};

// Directly render current node data
window.renderCurrentNodes = async function() {
    console.log('Rendering current nodes directly...');
    
    if (currentNodeStatus.length === 0) {
        console.log('No nodes to render');
        return;
    }
    
    // Create simple connections from current data
    const connections = [];
    for (let i = 0; i < currentNodeStatus.length - 1; i++) {
        connections.push({
            source: currentNodeStatus[i].node,
            target: currentNodeStatus[i + 1].node,
            status: 'enabled'
        });
    }
    
    const mermaidCode = generateMermaidDiagram(currentNodeStatus, connections);
    console.log('Generated code:', mermaidCode);
    
    const element = document.getElementById('mermaidDiagram');
    element.innerHTML = '';
    
    const wrapper = document.createElement('div');
    wrapper.className = 'mermaid';
    wrapper.textContent = mermaidCode;
    element.appendChild(wrapper);
    
    try {
        await mermaid.run();
        console.log('Diagram rendered successfully');
    } catch (e) {
        console.error('Failed to render:', e);
    }
};

// Check current diagram status
window.checkDiagramStatus = function() {
    console.log('=== Diagram Status Check ===');
    console.log('Session ID:', sessionId);
    console.log('Session Active:', sessionActive);
    console.log('Current Node Status:', currentNodeStatus);
    console.log('Current Edge Status:', currentEdgeStatus);
    
    const element = document.getElementById('mermaidDiagram');
    console.log('Diagram Element:', element);
    console.log('Diagram HTML:', element ? element.innerHTML.substring(0, 200) : 'null');
    
    const svgs = element ? element.querySelectorAll('svg') : [];
    console.log('SVG Elements Found:', svgs.length);
    
    if (currentNodeStatus.length > 0) {
        console.log('Nodes loaded:', currentNodeStatus.length);
        console.log('Sample nodes:', currentNodeStatus.slice(0, 3));
    } else {
        console.log('No nodes loaded yet');
    }
    
    return {
        sessionActive,
        nodeCount: currentNodeStatus.length,
        edgeCount: currentEdgeStatus.length,
        svgCount: svgs.length
    };
};

// Show a simple test diagram to verify Mermaid is working
window.showSimpleDiagram = async function() {
    console.log('Showing simple test diagram...');
    const element = document.getElementById('mermaidDiagram');
    element.innerHTML = '';
    
    const testCode = `graph TD
    A[Start] --> B[Process]
    B --> C[Decision]
    C -->|Yes| D[Action 1]
    C -->|No| E[Action 2]
    D --> F[End]
    E --> F`;
    
    const wrapper = document.createElement('div');
    wrapper.className = 'mermaid';
    wrapper.textContent = testCode;
    element.appendChild(wrapper);
    
    try {
        await mermaid.run();
        console.log('Simple diagram rendered successfully');
    } catch (e) {
        console.error('Failed to render simple diagram:', e);
    }
};

// Test node clicking functionality
window.testNodeClicking = function() {
    console.log('Testing node click detection...');
    const allGroups = document.querySelectorAll('g');
    console.log(`Found ${allGroups.length} g elements`);
    
    allGroups.forEach((g, index) => {
        const hasText = g.querySelector('text') !== null;
        const hasRect = g.querySelector('rect') !== null;
        const text = g.textContent || '';
        
        if (hasText && hasRect && text.trim()) {
            console.log(`Potential node ${index}:`, {
                id: g.id,
                text: text.trim(),
                hasClickHandler: g.onclick !== null,
                dataNodeId: g.getAttribute('data-node-id')
            });
        }
    });
    
    console.log('Current node status:', currentNodeStatus);
    console.log('To manually trigger node click, use: loadNodeDetails("nodeName")');
};

// Manual position adjustment for debugging
window.adjustDiagramPosition = function(x, y, scale) {
    console.log(`Manually adjusting position: x=${x}, y=${y}, scale=${scale}`);
    
    const diagram = document.getElementById('mermaidDiagram');
    if (!diagram) {
        console.error('No diagram element found');
        return;
    }
    
    if (x !== undefined) translateX = x;
    if (y !== undefined) translateY = y;
    if (scale !== undefined) currentScale = scale;
    
    diagram.style.transformOrigin = '0 0';
    diagram.style.transform = `translate(${translateX}px, ${translateY}px) scale(${currentScale})`;
    
    console.log('Applied transform:', diagram.style.transform);
    userInteracted = true; // Mark as manual adjustment
};

// Check diagram bounds and position
window.checkDiagramBounds = function() {
    console.log('=== Check Diagram Bounds ===');
    
    const wrapper = document.getElementById('mermaidWrapper');
    const diagram = document.getElementById('mermaidDiagram');
    const svg = diagram ? diagram.querySelector('svg') : null;
    
    if (!wrapper || !svg) {
        console.log('Missing elements - wrapper or SVG not found');
        return;
    }
    
    const wrapperRect = wrapper.getBoundingClientRect();
    const svgRect = svg.getBoundingClientRect();
    
    console.log('Wrapper bounds:', {
        left: wrapperRect.left,
        top: wrapperRect.top,
        right: wrapperRect.right,
        bottom: wrapperRect.bottom,
        width: wrapperRect.width,
        height: wrapperRect.height
    });
    
    console.log('SVG bounds:', {
        left: svgRect.left,
        top: svgRect.top,
        right: svgRect.right,
        bottom: svgRect.bottom,
        width: svgRect.width,
        height: svgRect.height
    });
    
    // Check if SVG is fully within wrapper
    const isVisible = svgRect.left >= wrapperRect.left && 
                     svgRect.top >= wrapperRect.top &&
                     svgRect.right <= wrapperRect.right && 
                     svgRect.bottom <= wrapperRect.bottom;
    
    console.log('Is fully visible:', isVisible);
    console.log('Current transform state:', {
        scale: currentScale,
        translateX: translateX,
        translateY: translateY
    });
    
    if (!isVisible) {
        console.log('⚠️ Diagram is not fully visible - fixing position...');
        forceCenterDiagram();
    } else {
        console.log('✅ Diagram is properly positioned');
    }
};

// Force center diagram (for debugging)
window.forceCenterDiagram = function() {
    console.log('=== Force Center Diagram ===');
    
    if (diagramController) {
        diagramController.fitToViewport();
    } else {
        console.log('DiagramController not initialized');
    }
};

// Test DiagramController functionality
window.testDiagramController = function() {
    console.log('=== Testing DiagramController ===');
    
    if (!diagramController) {
        console.error('DiagramController not initialized');
        return;
    }
    
    console.log('Current state:', diagramController.getState());
    console.log('Config:', diagramController.config);
    console.log('Container:', diagramController.container);
    console.log('Diagram:', diagramController.diagram);
    
    // Try a simple operation
    console.log('Testing zoom in...');
    diagramController.zoomIn();
    console.log('New state after zoom:', diagramController.getState());
    
    console.log('✅ DiagramController is working');
};

// Test function for debugging Mermaid diagram
window.testMermaidDiagram = function() {
    // Create test data
    const testNodes = [
        { node: 'start', status: 'finished' },
        { node: 'Step1', status: 'finished' },
        { node: 'Step2a', status: 'running' },
        { node: 'Step2b', status: 'pending' },
        { node: 'Step3', status: 'pending' },
        { node: 'end', status: 'pending' }
    ];
    
    const testConnections = [
        { source: 'start', target: 'Step1', status: 'enabled' },
        { source: 'Step1', target: 'Step2a', status: 'enabled', condition: 'if condition A' },
        { source: 'Step1', target: 'Step2b', status: 'disabled', condition: 'if condition B' },
        { source: 'Step2a', target: 'Step3', status: 'pending' },
        { source: 'Step2b', target: 'Step3', status: 'pending' },
        { source: 'Step3', target: 'end', status: 'pending' }
    ];
    
    const mermaidCode = generateMermaidDiagram(testNodes, testConnections);
    console.log('Test Mermaid Diagram:');
    console.log(mermaidCode);
    
    // Try to render it
    const element = document.getElementById('mermaidDiagram');
    const wrapper = document.createElement('div');
    wrapper.className = 'mermaid';
    wrapper.textContent = mermaidCode;
    
    element.innerHTML = '';
    element.appendChild(wrapper);
    
    mermaid.run().then(() => {
        console.log('Test diagram rendered successfully!');
    }).catch(err => {
        console.error('Test diagram failed:', err);
    });
}
