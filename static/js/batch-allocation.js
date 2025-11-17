/**
 * Batch Allocation Module
 * Handles batch selection, FEFO/FIFO auto-allocation, and drawer UI
 */

const BatchAllocation = (function() {
    // State
    let currentItemId = null;
    let currentItemData = null;
    let currentBatches = {};
    let currentAllocations = {};
    
    // DOM elements
    const elements = {
        overlay: null,
        drawer: null,
        closeBtn: null,
        cancelBtn: null,
        applyBtn: null,
        autoAllocateBtn: null,
        itemName: null,
        requestedQty: null,
        allocatedQty: null,
        remainingQty: null,
        issuanceOrder: null,
        autoAllocateRule: null,
        batchList: null,
        emptyState: null,
        loadingState: null,
        batchItemTemplate: null
    };
    
    /**
     * Initialize the batch allocation module
     */
    function init() {
        // Get DOM elements
        elements.overlay = document.getElementById('batchDrawerOverlay');
        elements.drawer = document.getElementById('batchDrawer');
        elements.closeBtn = document.getElementById('batchDrawerClose');
        elements.cancelBtn = document.getElementById('batchDrawerCancel');
        elements.applyBtn = document.getElementById('batchDrawerApply');
        elements.autoAllocateBtn = document.getElementById('batchAutoAllocateBtn');
        elements.itemName = document.getElementById('batchDrawerItemName');
        elements.requestedQty = document.getElementById('batchRequestedQty');
        elements.allocatedQty = document.getElementById('batchAllocatedQty');
        elements.remainingQty = document.getElementById('batchRemainingQty');
        elements.issuanceOrder = document.getElementById('batchIssuanceOrder');
        elements.autoAllocateRule = document.getElementById('batchAutoAllocateRule');
        elements.batchList = document.getElementById('batchList');
        elements.emptyState = document.getElementById('batchEmptyState');
        elements.loadingState = document.getElementById('batchLoadingState');
        elements.batchItemTemplate = document.getElementById('batchItemTemplate');
        
        // Attach event listeners
        if (elements.closeBtn) elements.closeBtn.addEventListener('click', closeDrawer);
        if (elements.cancelBtn) elements.cancelBtn.addEventListener('click', closeDrawer);
        if (elements.applyBtn) elements.applyBtn.addEventListener('click', applyAllocations);
        if (elements.autoAllocateBtn) elements.autoAllocateBtn.addEventListener('click', autoAllocate);
        if (elements.overlay) elements.overlay.addEventListener('click', closeDrawer);
        
        // Expose open function globally
        window.openBatchDrawer = openDrawer;
    }
    
    /**
     * Open the batch drawer for a specific item
     * @param {number} itemId - Item ID
     * @param {string} itemName - Item name
     * @param {number} requestedQty - Requested quantity
     */
    function openDrawer(itemId, itemName, requestedQty) {
        currentItemId = itemId;
        currentItemData = {
            itemId: itemId,
            itemName: itemName,
            requestedQty: requestedQty
        };
        
        // Update header
        elements.itemName.textContent = `${itemName}`;
        elements.requestedQty.textContent = formatNumber(requestedQty);
        
        // Show drawer
        elements.overlay.classList.add('active');
        elements.drawer.classList.add('active');
        document.body.style.overflow = 'hidden';
        
        // Load batches
        loadBatches(itemId);
    }
    
    /**
     * Close the batch drawer
     */
    function closeDrawer() {
        elements.overlay.classList.remove('active');
        elements.drawer.classList.remove('active');
        document.body.style.overflow = '';
        
        // Reset state after animation
        setTimeout(() => {
            currentItemId = null;
            currentItemData = null;
            currentBatches = {};
            currentAllocations = {};
            elements.batchList.innerHTML = '';
        }, 300);
    }
    
    /**
     * Load available batches for the current item
     * @param {number} itemId - Item ID
     */
    async function loadBatches(itemId) {
        showLoading();
        
        try {
            const response = await fetch(`/packaging/api/item/${itemId}/batches`);
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Failed to load batches');
            }
            
            // Store item configuration
            currentItemData.issuanceOrder = data.issuance_order || 'FIFO';
            currentItemData.canExpire = data.can_expire;
            currentItemData.isBatched = data.is_batched;
            
            // Update issuance order display
            elements.issuanceOrder.textContent = data.issuance_order || 'FIFO';
            elements.autoAllocateRule.textContent = data.issuance_order || 'FIFO';
            
            // Flatten batches from all warehouses
            currentBatches = {};
            const allBatches = [];
            
            for (const [warehouseId, batches] of Object.entries(data.batches)) {
                batches.forEach(batch => {
                    currentBatches[batch.batch_id] = batch;
                    allBatches.push(batch);
                });
            }
            
            // Load existing allocations from form
            loadExistingAllocations();
            
            // Render batches
            renderBatches(allBatches);
            hideLoading();
            
        } catch (error) {
            console.error('Error loading batches:', error);
            hideLoading();
            showEmptyState();
            alert('Failed to load batches: ' + error.message);
        }
    }
    
    /**
     * Load existing allocations from the main form
     */
    function loadExistingAllocations() {
        currentAllocations = {};
        
        // Look for hidden inputs with pattern: batch_allocation_{itemId}_{batchId}
        const inputs = document.querySelectorAll(`input[name^="batch_allocation_${currentItemId}_"]`);
        
        inputs.forEach(input => {
            const parts = input.name.split('_');
            if (parts.length >= 4) {
                const batchId = parseInt(parts[3]);
                const qty = parseFloat(input.value) || 0;
                if (qty > 0) {
                    currentAllocations[batchId] = qty;
                }
            }
        });
        
        updateTotals();
    }
    
    /**
     * Render the batch list
     * @param {Array} batches - Array of batch objects
     */
    function renderBatches(batches) {
        elements.batchList.innerHTML = '';
        
        if (batches.length === 0) {
            showEmptyState();
            return;
        }
        
        batches.forEach(batch => {
            const batchElement = createBatchElement(batch);
            elements.batchList.appendChild(batchElement);
        });
        
        hideEmptyState();
    }
    
    /**
     * Create a batch DOM element from template
     * @param {Object} batch - Batch data
     * @returns {HTMLElement} Batch element
     */
    function createBatchElement(batch) {
        const template = elements.batchItemTemplate.content.cloneNode(true);
        const container = template.querySelector('.batch-item');
        
        // Set batch ID
        container.dataset.batchId = batch.batch_id;
        
        // Populate batch details
        container.querySelector('.batch-number').textContent = batch.batch_no;
        container.querySelector('.batch-warehouse-name').textContent = batch.warehouse_name;
        container.querySelector('.batch-batch-date').textContent = formatDate(batch.batch_date);
        container.querySelector('.batch-expiry-date').textContent = formatDate(batch.expiry_date) || 'N/A';
        container.querySelector('.batch-available-qty').textContent = formatNumber(batch.available_qty);
        
        const sizeUom = batch.size_spec ? `${batch.size_spec} ${batch.uom_code}` : batch.uom_code;
        container.querySelector('.batch-size-uom').textContent = sizeUom;
        
        // Check if expired or expiring soon
        const today = new Date();
        const expiryDate = batch.expiry_date ? new Date(batch.expiry_date) : null;
        
        if (expiryDate) {
            const daysToExpiry = Math.ceil((expiryDate - today) / (1000 * 60 * 60 * 24));
            
            if (daysToExpiry < 0) {
                container.classList.add('expired');
                const statusBadge = document.createElement('span');
                statusBadge.className = 'batch-item-status expired';
                statusBadge.textContent = 'Expired';
                container.querySelector('.batch-item-status-container').appendChild(statusBadge);
            } else if (daysToExpiry <= 30) {
                const statusBadge = document.createElement('span');
                statusBadge.className = 'batch-item-status expiring-soon';
                statusBadge.textContent = `Expires in ${daysToExpiry}d`;
                container.querySelector('.batch-item-status-container').appendChild(statusBadge);
            }
        }
        
        // Allocation input
        const input = container.querySelector('[data-batch-allocation-input]');
        input.max = batch.available_qty;
        input.value = currentAllocations[batch.batch_id] || '';
        
        // Disable if expired
        if (container.classList.contains('expired')) {
            input.disabled = true;
        }
        
        // Input change event
        input.addEventListener('input', () => {
            const qty = parseFloat(input.value) || 0;
            
            // Validate
            if (qty > batch.available_qty) {
                input.value = batch.available_qty;
            }
            if (qty < 0) {
                input.value = 0;
            }
            
            // Update allocations
            const finalQty = parseFloat(input.value) || 0;
            if (finalQty > 0) {
                currentAllocations[batch.batch_id] = finalQty;
                container.classList.add('has-allocation');
            } else {
                delete currentAllocations[batch.batch_id];
                container.classList.remove('has-allocation');
            }
            
            updateTotals();
        });
        
        // "Use Max" button
        const maxBtn = container.querySelector('[data-batch-max-btn]');
        maxBtn.addEventListener('click', () => {
            const remainingQty = currentItemData.requestedQty - getTotalAllocated();
            const maxQty = Math.min(batch.available_qty, remainingQty + (currentAllocations[batch.batch_id] || 0));
            
            input.value = maxQty;
            input.dispatchEvent(new Event('input'));
        });
        
        // Add has-allocation class if already allocated
        if (currentAllocations[batch.batch_id]) {
            container.classList.add('has-allocation');
        }
        
        return container;
    }
    
    /**
     * Auto-allocate batches using FEFO/FIFO rules
     */
    async function autoAllocate() {
        const requestedQty = currentItemData.requestedQty;
        
        try {
            const response = await fetch(`/packaging/api/item/${currentItemId}/auto-allocate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    requested_qty: requestedQty
                })
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Auto-allocation failed');
            }
            
            // Clear existing allocations
            currentAllocations = {};
            
            // Apply new allocations
            data.allocations.forEach(allocation => {
                currentAllocations[allocation.batch_id] = allocation.allocated_qty;
            });
            
            // Update UI
            const batchElements = elements.batchList.querySelectorAll('.batch-item');
            batchElements.forEach(el => {
                const batchId = parseInt(el.dataset.batchId);
                const input = el.querySelector('[data-batch-allocation-input]');
                
                if (currentAllocations[batchId]) {
                    input.value = currentAllocations[batchId];
                    el.classList.add('has-allocation');
                } else {
                    input.value = '';
                    el.classList.remove('has-allocation');
                }
            });
            
            updateTotals();
            
        } catch (error) {
            console.error('Error auto-allocating:', error);
            alert('Failed to auto-allocate: ' + error.message);
        }
    }
    
    /**
     * Apply allocations to the main form
     */
    function applyAllocations() {
        // Remove existing allocation inputs for this item
        const existingInputs = document.querySelectorAll(`input[name^="batch_allocation_${currentItemId}_"]`);
        existingInputs.forEach(input => input.remove());
        
        // Create new hidden inputs for each allocation
        const form = document.querySelector('form');
        
        for (const [batchId, qty] of Object.entries(currentAllocations)) {
            if (qty > 0) {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = `batch_allocation_${currentItemId}_${batchId}`;
                input.value = qty;
                form.appendChild(input);
            }
        }
        
        // Update the main page display
        updateMainPageDisplay();
        
        // Close drawer
        closeDrawer();
    }
    
    /**
     * Update the main page to show allocated quantities
     */
    function updateMainPageDisplay() {
        const totalAllocated = getTotalAllocated();
        
        // Update allocated quantity display in main form (if element exists)
        const allocatedDisplay = document.getElementById(`allocated_${currentItemId}`);
        if (allocatedDisplay) {
            allocatedDisplay.textContent = formatNumber(totalAllocated);
        }
        
        // Update "Select Batches" button to show allocation count
        const selectBtn = document.querySelector(`[data-item-id="${currentItemId}"] .select-batches-btn`);
        if (selectBtn) {
            const batchCount = Object.keys(currentAllocations).length;
            if (batchCount > 0) {
                selectBtn.innerHTML = `<i class="bi bi-box-seam"></i> ${batchCount} Batch${batchCount > 1 ? 'es' : ''} Selected`;
                selectBtn.classList.add('btn-success');
                selectBtn.classList.remove('btn-outline');
            } else {
                selectBtn.innerHTML = '<i class="bi bi-box-seam"></i> Select Batches';
                selectBtn.classList.remove('btn-success');
                selectBtn.classList.add('btn-outline');
            }
        }
    }
    
    /**
     * Calculate total allocated quantity
     * @returns {number} Total allocated
     */
    function getTotalAllocated() {
        return Object.values(currentAllocations).reduce((sum, qty) => sum + qty, 0);
    }
    
    /**
     * Update summary totals
     */
    function updateTotals() {
        const requested = currentItemData.requestedQty;
        const allocated = getTotalAllocated();
        const remaining = Math.max(0, requested - allocated);
        
        elements.allocatedQty.textContent = formatNumber(allocated);
        elements.remainingQty.textContent = formatNumber(remaining);
        
        // Update remaining color
        if (remaining === 0) {
            elements.remainingQty.classList.remove('warning');
            elements.remainingQty.classList.add('highlight');
        } else {
            elements.remainingQty.classList.remove('highlight');
            elements.remainingQty.classList.add('warning');
        }
    }
    
    /**
     * Show loading state
     */
    function showLoading() {
        elements.batchList.style.display = 'none';
        elements.emptyState.style.display = 'none';
        elements.loadingState.style.display = 'flex';
    }
    
    /**
     * Hide loading state
     */
    function hideLoading() {
        elements.loadingState.style.display = 'none';
        elements.batchList.style.display = 'flex';
    }
    
    /**
     * Show empty state
     */
    function showEmptyState() {
        elements.batchList.style.display = 'none';
        elements.emptyState.style.display = 'block';
    }
    
    /**
     * Hide empty state
     */
    function hideEmptyState() {
        elements.emptyState.style.display = 'none';
    }
    
    /**
     * Format a number with commas
     * @param {number} num - Number to format
     * @returns {string} Formatted number
     */
    function formatNumber(num) {
        if (num === null || num === undefined) return '0';
        return parseFloat(num).toLocaleString('en-US', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 4
        });
    }
    
    /**
     * Format a date string
     * @param {string} dateStr - ISO date string
     * @returns {string} Formatted date
     */
    function formatDate(dateStr) {
        if (!dateStr) return null;
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    }
    
    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
    // Public API
    return {
        openDrawer: openDrawer,
        closeDrawer: closeDrawer
    };
})();
