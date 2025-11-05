/**
 * DiagramController - A stable and reliable diagram positioning and zoom controller
 * Complete rewrite to fix fundamental issues with the previous implementation
 */

class DiagramController {
    constructor() {
        // State management
        this.state = {
            scale: 1,
            translateX: 0,
            translateY: 0,
            isDragging: false,
            dragStartX: 0,
            dragStartY: 0,
            lastX: 0,
            lastY: 0,
            initialized: false,
            isRendering: false
        };
        
        // Configuration
        this.config = {
            minScale: 0.1,      // Allow much smaller zoom
            maxScale: 10,       // Allow much larger zoom
            scaleStep: 0.1,     // Zoom step size
            wheelScaleFactor: 0.002,  // Mouse wheel sensitivity
            animationDuration: 0,  // No animation by default to prevent flicker
            fitPadding: 50,     // Padding when fitting to viewport
            enableStatePersistence: true,  // Enable saving state to localStorage
            storageKey: 'diagramControllerState'  // localStorage key
        };
        
        // Element references
        this.container = null;
        this.diagram = null;
        this.svg = null;
        
        // Bind methods
        this.handleWheel = this.handleWheel.bind(this);
        this.handleMouseDown = this.handleMouseDown.bind(this);
        this.handleMouseMove = this.handleMouseMove.bind(this);
        this.handleMouseUp = this.handleMouseUp.bind(this);
        this.handleResize = this.handleResize.bind(this);
    }
    
    /**
     * Initialize the controller with target elements
     */
    init(containerId = 'mermaidWrapper', diagramId = 'mermaidDiagram') {
        console.log('[DiagramController] Initializing...');
        
        this.container = document.getElementById(containerId);
        this.diagram = document.getElementById(diagramId);
        
        if (!this.container || !this.diagram) {
            console.error('[DiagramController] Required elements not found');
            return false;
        }
        
        // Setup styles for predictable behavior
        this.setupStyles();
        
        // Attach event listeners
        this.attachEventListeners();
        
        // Load saved state if available
        this.loadState();
        
        this.state.initialized = true;
        console.log('[DiagramController] Initialized successfully');
        return true;
    }
    
    /**
     * Setup required styles
     */
    setupStyles() {
        // Ensure diagram has relative positioning for transform to work
        this.diagram.style.position = 'relative';
        this.diagram.style.transformOrigin = '0 0'; // Always use top-left origin
        
        // Remove any conflicting styles
        this.diagram.style.margin = '0';
        this.diagram.style.padding = '0';
        
        // Ensure container doesn't interfere
        this.container.style.overflow = 'hidden';
        this.container.style.position = 'relative';
    }
    
    /**
     * Attach event listeners
     */
    attachEventListeners() {
        // Mouse events for dragging
        this.container.addEventListener('mousedown', this.handleMouseDown);
        window.addEventListener('mousemove', this.handleMouseMove);
        window.addEventListener('mouseup', this.handleMouseUp);
        
        // Wheel event for zooming
        this.container.addEventListener('wheel', this.handleWheel, { passive: false });
        
        // Window resize
        window.addEventListener('resize', this.handleResize);
    }
    
    /**
     * Remove all event listeners (for cleanup)
     */
    destroy() {
        this.container?.removeEventListener('mousedown', this.handleMouseDown);
        window.removeEventListener('mousemove', this.handleMouseMove);
        window.removeEventListener('mouseup', this.handleMouseUp);
        this.container?.removeEventListener('wheel', this.handleWheel);
        window.removeEventListener('resize', this.handleResize);
    }
    
    /**
     * Apply current transform state to the diagram
     */
    applyTransform(animate = false) {
        if (!this.diagram) return;
        
        const transform = `translate(${this.state.translateX}px, ${this.state.translateY}px) scale(${this.state.scale})`;
        
        // Apply transition only if explicitly requested
        if (animate) {
            this.diagram.style.transition = `transform ${this.config.animationDuration}ms ease-out`;
            setTimeout(() => {
                this.diagram.style.transition = '';
            }, this.config.animationDuration);
        } else {
            this.diagram.style.transition = '';
        }
        
        this.diagram.style.transform = transform;
        
        // Save state after applying transform
        this.saveState();
        
        // Log for debugging
        console.log(`[DiagramController] Transform applied: scale=${this.state.scale.toFixed(2)}, translate=(${Math.round(this.state.translateX)}, ${Math.round(this.state.translateY)})`);
    }
    
    /**
     * Handle mouse wheel for zooming
     */
    handleWheel(event) {
        event.preventDefault();
        
        if (!this.state.initialized || this.state.isRendering) return;
        
        // Get mouse position relative to container
        const rect = this.container.getBoundingClientRect();
        const mouseX = event.clientX - rect.left;
        const mouseY = event.clientY - rect.top;
        
        // Calculate new scale
        const delta = -event.deltaY * this.config.wheelScaleFactor;
        const oldScale = this.state.scale;
        const newScale = Math.max(this.config.minScale, Math.min(this.config.maxScale, oldScale + delta));
        
        if (newScale === oldScale) return;
        
        // Calculate the point to zoom around (in diagram space)
        const zoomPointX = (mouseX - this.state.translateX) / oldScale;
        const zoomPointY = (mouseY - this.state.translateY) / oldScale;
        
        // Update scale
        this.state.scale = newScale;
        
        // Adjust translation to zoom around mouse position
        this.state.translateX = mouseX - zoomPointX * newScale;
        this.state.translateY = mouseY - zoomPointY * newScale;
        
        this.applyTransform(false);
    }
    
    /**
     * Handle mouse down for dragging
     */
    handleMouseDown(event) {
        // Only handle left mouse button
        if (event.button !== 0) return;
        
        // Check if clicking on an interactive element
        const target = event.target;
        if (target.closest('g[data-node-id]') || 
            target.tagName === 'text' || 
            target.tagName === 'rect') {
            return; // Let node click handlers work
        }
        
        this.state.isDragging = true;
        this.state.dragStartX = event.clientX;
        this.state.dragStartY = event.clientY;
        this.state.lastX = this.state.translateX;
        this.state.lastY = this.state.translateY;
        
        this.container.style.cursor = 'grabbing';
        event.preventDefault();
    }
    
    /**
     * Handle mouse move for dragging
     */
    handleMouseMove(event) {
        if (!this.state.isDragging) return;
        
        const deltaX = event.clientX - this.state.dragStartX;
        const deltaY = event.clientY - this.state.dragStartY;
        
        this.state.translateX = this.state.lastX + deltaX;
        this.state.translateY = this.state.lastY + deltaY;
        
        this.applyTransform(false);
    }
    
    /**
     * Handle mouse up to stop dragging
     */
    handleMouseUp(event) {
        if (this.state.isDragging) {
            this.state.isDragging = false;
            this.container.style.cursor = '';
        }
    }
    
    /**
     * Handle window resize
     */
    handleResize() {
        // Optionally refit diagram on resize
        // this.fitToViewport();
    }
    
    /**
     * Zoom in
     */
    zoomIn() {
        const centerX = this.container.clientWidth / 2;
        const centerY = this.container.clientHeight / 2;
        
        const oldScale = this.state.scale;
        const newScale = Math.min(this.config.maxScale, oldScale + this.config.scaleStep);
        
        if (newScale === oldScale) return;
        
        // Zoom around center
        const scaleFactor = newScale / oldScale;
        this.state.scale = newScale;
        this.state.translateX = centerX - (centerX - this.state.translateX) * scaleFactor;
        this.state.translateY = centerY - (centerY - this.state.translateY) * scaleFactor;
        
        this.applyTransform(true);
    }
    
    /**
     * Zoom out
     */
    zoomOut() {
        const centerX = this.container.clientWidth / 2;
        const centerY = this.container.clientHeight / 2;
        
        const oldScale = this.state.scale;
        const newScale = Math.max(this.config.minScale, oldScale - this.config.scaleStep);
        
        if (newScale === oldScale) return;
        
        // Zoom around center
        const scaleFactor = newScale / oldScale;
        this.state.scale = newScale;
        this.state.translateX = centerX - (centerX - this.state.translateX) * scaleFactor;
        this.state.translateY = centerY - (centerY - this.state.translateY) * scaleFactor;
        
        this.applyTransform(true);
    }
    
    /**
     * Reset zoom to 1:1
     */
    resetZoom() {
        this.state.scale = 1;
        this.state.translateX = 0;
        this.state.translateY = 0;
        this.applyTransform(true);
    }
    
    /**
     * Fit diagram to viewport - NEW STABLE IMPLEMENTATION
     */
    fitToViewport() {
        console.log('[DiagramController] Fitting to viewport...');
        
        if (!this.container || !this.diagram) {
            console.error('[DiagramController] Missing elements');
            return;
        }
        
        // Mark as rendering to prevent interference
        this.state.isRendering = true;
        
        // Find the SVG element
        this.svg = this.diagram.querySelector('svg');
        if (!this.svg) {
            console.error('[DiagramController] No SVG found');
            this.state.isRendering = false;
            return;
        }
        
        // Reset transform to get accurate measurements
        this.diagram.style.transform = 'none';
        
        // Wait a frame for the reset to take effect
        requestAnimationFrame(() => {
            // Get container dimensions
            const containerRect = this.container.getBoundingClientRect();
            const containerWidth = containerRect.width;
            const containerHeight = containerRect.height;
            
            // Get SVG dimensions
            let svgWidth, svgHeight;
            
            // Try multiple methods to get accurate dimensions
            if (this.svg.viewBox && this.svg.viewBox.baseVal) {
                svgWidth = this.svg.viewBox.baseVal.width;
                svgHeight = this.svg.viewBox.baseVal.height;
            } else {
                const bbox = this.svg.getBBox();
                svgWidth = bbox.width;
                svgHeight = bbox.height;
            }
            
            // Fallback to client dimensions
            if (!svgWidth || !svgHeight) {
                const svgRect = this.svg.getBoundingClientRect();
                svgWidth = svgRect.width;
                svgHeight = svgRect.height;
            }
            
            console.log(`[DiagramController] Container: ${containerWidth}x${containerHeight}, SVG: ${svgWidth}x${svgHeight}`);
            
            if (!svgWidth || !svgHeight) {
                console.error('[DiagramController] Unable to determine SVG dimensions');
                this.state.isRendering = false;
                return;
            }
            
            // Calculate scale to fit
            const padding = this.config.fitPadding;
            const availableWidth = containerWidth - padding * 2;
            const availableHeight = containerHeight - padding * 2;
            
            const scaleX = availableWidth / svgWidth;
            const scaleY = availableHeight / svgHeight;
            const scale = Math.min(scaleX, scaleY, 2); // Don't scale up more than 2x
            
            // Calculate center position
            const scaledWidth = svgWidth * scale;
            const scaledHeight = svgHeight * scale;
            const translateX = (containerWidth - scaledWidth) / 2;
            const translateY = (containerHeight - scaledHeight) / 2;
            
            // Update state
            this.state.scale = scale;
            this.state.translateX = translateX;
            this.state.translateY = translateY;
            
            // Apply transform
            this.applyTransform(false);
            
            this.state.isRendering = false;
            console.log('[DiagramController] Fit complete');
        });
    }
    
    /**
     * Get current state (for debugging)
     */
    getState() {
        return { ...this.state };
    }
    
    /**
     * Set state manually (for debugging)
     */
    setState(newState) {
        Object.assign(this.state, newState);
        this.applyTransform();
    }
    
    /**
     * Save current view state to localStorage
     */
    saveState() {
        if (!this.config.enableStatePersistence) return;
        
        try {
            const stateToSave = {
                scale: this.state.scale,
                translateX: this.state.translateX,
                translateY: this.state.translateY,
                timestamp: Date.now()
            };
            
            localStorage.setItem(this.config.storageKey, JSON.stringify(stateToSave));
            console.log('[DiagramController] State saved to localStorage');
        } catch (e) {
            console.warn('[DiagramController] Failed to save state:', e);
        }
    }
    
    /**
     * Load saved state from localStorage
     */
    loadState() {
        if (!this.config.enableStatePersistence) return false;
        
        try {
            const savedState = localStorage.getItem(this.config.storageKey);
            if (savedState) {
                const parsed = JSON.parse(savedState);
                
                // Check if saved state is not too old (24 hours)
                const maxAge = 24 * 60 * 60 * 1000; // 24 hours in ms
                if (parsed.timestamp && (Date.now() - parsed.timestamp) < maxAge) {
                    this.state.scale = parsed.scale || 1;
                    this.state.translateX = parsed.translateX || 0;
                    this.state.translateY = parsed.translateY || 0;
                    
                    // Don't apply transform immediately during init
                    // Let the diagram render first, then apply
                    console.log('[DiagramController] State loaded from localStorage (not yet applied)');
                    return true;
                } else {
                    // Clear old state
                    localStorage.removeItem(this.config.storageKey);
                    console.log('[DiagramController] Cleared old saved state');
                }
            }
        } catch (e) {
            console.warn('[DiagramController] Failed to load state:', e);
        }
        
        return false;
    }
    
    /**
     * Clear saved state
     */
    clearSavedState() {
        try {
            localStorage.removeItem(this.config.storageKey);
            console.log('[DiagramController] Saved state cleared');
        } catch (e) {
            console.warn('[DiagramController] Failed to clear saved state:', e);
        }
    }
    
    /**
     * Check if there is a saved state available
     */
    hasSavedState() {
        if (!this.config.enableStatePersistence) return false;
        
        try {
            const savedState = localStorage.getItem(this.config.storageKey);
            if (savedState) {
                const parsed = JSON.parse(savedState);
                const maxAge = 24 * 60 * 60 * 1000; // 24 hours
                return parsed.timestamp && (Date.now() - parsed.timestamp) < maxAge;
            }
        } catch (e) {
            console.warn('[DiagramController] Error checking saved state:', e);
        }
        
        return false;
    }
}

// Export as global for use in existing code
window.DiagramController = DiagramController;
