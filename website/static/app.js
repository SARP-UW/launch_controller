/**
 * Ground Control System - Frontend Application
 * Manages valve control, pressure sensor monitoring, and procedure execution
 * for liquid rocket engine test and launch operations.
 */

// Enable/disable console logging
const LOG_STATUS = true;
const LOG_ERRORS = true;

// Polling intervals (ms)
const HEARTBEAT_INTERVAL = 100;
const VALVE_POLL_INTERVAL = 100;
const SENSOR_POLL_INTERVAL = 100;
const SAFE_MODE_POLL_INTERVAL = 100;

// Chart configuration
const CHART_MAX_POINTS = 100;
const CHART_COLORS = [
    '#3b82f6', '#22c55e', '#f59e0b', '#ef4444', 
    '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16'
];

// Application state
const State = {
    connected: false,
    safeMode: false,
    valves: [],
    sensors: [],
    sensorHistory: {},
    sensorCharts: {},
    selectedProcedure: null,
    completedSteps: new Set(),
    currentRequirementsMet: {}
};

// Logging utilities
function logStatus(message) {
    if (LOG_STATUS) console.log(`[STATUS] ${new Date().toISOString()} - ${message}`);
}

function logError(message, error = null) {
    if (LOG_ERRORS) {
        console.error(`[ERROR] ${new Date().toISOString()} - ${message}`);
        if (error) console.error(error);
    }
}

/**
 * Modal dialog management
 */
const Modal = {
    show(title, content, actions) {
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-content').innerHTML = content;
        
        const actionsContainer = document.getElementById('modal-actions');
        actionsContainer.innerHTML = '';
        
        actions.forEach(action => {
            const btn = document.createElement('button');
            btn.className = `modal-btn ${action.type || 'secondary'}`;
            btn.textContent = action.label;
            btn.onclick = () => {
                if (action.callback) action.callback();
                if (action.closeOnClick !== false) Modal.close();
            };
            actionsContainer.appendChild(btn);
        });
        
        document.getElementById('modal-overlay').classList.remove('hidden');
    },
    
    close() {
        document.getElementById('modal-overlay').classList.add('hidden');
    },
    
    confirm(title, message, onConfirm, confirmLabel = 'Confirm', confirmType = 'primary') {
        Modal.show(title, `<p>${message}</p>`, [
            { label: 'Cancel', type: 'secondary' },
            { label: confirmLabel, type: confirmType, callback: onConfirm }
        ]);
    },
    
    warning(title, message, onContinue) {
        Modal.show(title, message, [
            { label: 'Cancel', type: 'secondary' },
            { label: 'Continue Anyway', type: 'warning', callback: onContinue }
        ]);
    }
};

/**
 * API communication layer
 */
const API = {
    async request(endpoint, options = {}) {
        try {
            const response = await fetch(endpoint, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.message || `HTTP ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            logError(`API request failed: ${endpoint}`, error);
            throw error;
        }
    },
    
    async sendHeartbeat() {
        return this.request('/api/send_heartbeat');
    },
    
    async getServerStatus() {
        return this.request('/api/get_server_status');
    },
    
    async getValveInfo() {
        return this.request('/api/get_valve_info');
    },
    
    async getSensorInfo() {
        return this.request('/api/get_sensor_info');
    },
    
    async setValveStates(states) {
        return this.request('/api/set_valve_states', {
            method: 'POST',
            body: JSON.stringify(states)
        });
    },
    
    async getSafeMode() {
        return this.request('/api/get_safe_mode');
    },
    
    async setSafeMode(enabled) {
        return this.request('/api/set_safe_mode', {
            method: 'POST',
            body: JSON.stringify({ safe_mode: enabled })
        });
    }
};

/**
 * Updates connection status indicator in the UI
 */
function updateConnectionStatus(connected) {
    const indicator = document.getElementById('connection-status');
    const statusText = indicator.querySelector('.status-text');
    
    if (connected) {
        indicator.classList.remove('disconnected');
        indicator.classList.add('connected');
        statusText.textContent = 'Connected';
    } else {
        indicator.classList.remove('connected');
        indicator.classList.add('disconnected');
        statusText.textContent = 'Disconnected';
    }
    
    if (State.connected !== connected) {
        State.connected = connected;
        logStatus(`Connection status: ${connected ? 'Connected' : 'Disconnected'}`);
    }
}

/**
 * Sends periodic heartbeat to maintain connection
 */
async function heartbeatLoop() {
    try {
        await API.sendHeartbeat();
        updateConnectionStatus(true);
    } catch (error) {
        updateConnectionStatus(false);
    }
    setTimeout(heartbeatLoop, HEARTBEAT_INTERVAL);
}

/**
 * Creates valve control card HTML
 */
function createValveCard(valve) {
    const isOpen = valve.current_state === 'open';
    return `
        <div class="valve-card" data-valve-id="${valve.id}">
            <div class="valve-header">
                <span class="valve-name">${valve.name}</span>
                <span class="valve-id">ID: ${valve.id}</span>
            </div>
            <div class="valve-controls">
                <button class="valve-btn open-btn ${isOpen ? 'active' : ''}" 
                        onclick="setValveState(${valve.id}, 'open')">Open</button>
                <button class="valve-btn close-btn ${!isOpen ? 'active' : ''}" 
                        onclick="setValveState(${valve.id}, 'closed')">Closed</button>
            </div>
        </div>
    `;
}

/**
 * Renders all valve cards
 */
function renderValves() {
    const container = document.getElementById('valves-container');
    
    if (State.valves.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">🔧</div>
                <p>No valves configured</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = State.valves.map(createValveCard).join('');
}

/**
 * Updates valve UI based on current state
 */
function updateValveUI(valveId, state) {
    const card = document.querySelector(`.valve-card[data-valve-id="${valveId}"]`);
    if (!card) return;
    
    const openBtn = card.querySelector('.open-btn');
    const closeBtn = card.querySelector('.close-btn');
    
    if (state === 'open') {
        openBtn.classList.add('active');
        closeBtn.classList.remove('active');
    } else {
        openBtn.classList.remove('active');
        closeBtn.classList.add('active');
    }
}

/**
 * Checks if a valve state change would result in an invalid configuration
 * @returns Array of invalid state descriptions, empty if valid
 */
function checkInvalidValveState(valveId, newState) {
    const violations = [];
    const simulatedStates = {};
    
    State.valves.forEach(v => {
        simulatedStates[v.id] = v.current_state;
    });
    simulatedStates[valveId] = newState;
    
    if (!CONFIG.invalidValveStates || !Array.isArray(CONFIG.invalidValveStates)) {
        return violations;
    }
    
    CONFIG.invalidValveStates.forEach((rule, index) => {
        const openValves = rule.open || [];
        const closedValves = rule.closed || [];
        
        const openMatch = openValves.every(id => simulatedStates[id] === 'open');
        const closedMatch = closedValves.every(id => simulatedStates[id] === 'closed');
        
        if (openMatch && closedMatch && (openValves.length > 0 || closedValves.length > 0)) {
            const openNames = openValves.map(id => {
                const v = State.valves.find(valve => valve.id === id);
                return v ? v.name : `Valve ${id}`;
            });
            const closedNames = closedValves.map(id => {
                const v = State.valves.find(valve => valve.id === id);
                return v ? v.name : `Valve ${id}`;
            });
            
            let desc = 'Invalid state: ';
            if (openNames.length > 0) desc += `${openNames.join(', ')} open`;
            if (openNames.length > 0 && closedNames.length > 0) desc += ' and ';
            if (closedNames.length > 0) desc += `${closedNames.join(', ')} closed`;
            violations.push(desc);
        }
    });
    
    return violations;
}

/**
 * Sets valve state with validation
 */
async function setValveState(valveId, state) {
    const violations = checkInvalidValveState(valveId, state);
    
    if (violations.length > 0) {
        const valve = State.valves.find(v => v.id === valveId);
        const valveName = valve ? valve.name : `Valve ${valveId}`;
        
        Modal.warning(
            'Invalid Valve Configuration',
            `<p>Setting <strong>${valveName}</strong> to <strong>${state}</strong> would result in an invalid configuration:</p>
            <ul>${violations.map(v => `<li>${v}</li>`).join('')}</ul>`,
            () => executeValveChange(valveId, state)
        );
        return;
    }
    
    executeValveChange(valveId, state);
}

/**
 * Executes valve state change via API
 */
async function executeValveChange(valveId, state) {
    try {
        await API.setValveStates({ [valveId]: state });
        logStatus(`Valve ${valveId} set to ${state}`);
        await pollValves(); // Immediately fetch updated state from server
    } catch (error) {
        logError(`Failed to set valve ${valveId} to ${state}`, error);
        Modal.show('Error', `<p>Failed to set valve state: ${error.message}</p>`, [
            { label: 'OK', type: 'primary' }
        ]);
    }
}

/**
 * Polls valve states from server
 */
async function pollValves() {
    try {
        const valves = await API.getValveInfo();
        State.valves = valves;
        
        valves.forEach(valve => {
            updateValveUI(valve.id, valve.current_state);
        });
        
        updateAllStepRequirements();
    } catch (error) {
        logError('Failed to poll valve states', error);
    }
}

/**
 * Valve polling loop
 */
async function valvePollingLoop() {
    if (State.connected) {
        await pollValves();
    }
    setTimeout(valvePollingLoop, VALVE_POLL_INTERVAL);
}

/**
 * Creates sensor display card HTML
 */
function createSensorCard(sensor, index) {
    const colorIndex = index % CHART_COLORS.length;
    return `
        <div class="sensor-card" data-sensor-id="${sensor.id}">
            <div class="sensor-header">
                <span class="sensor-name">${sensor.name}</span>
                <span class="sensor-id">ID: ${sensor.id}</span>
            </div>
            <div class="sensor-value" id="sensor-value-${sensor.id}">-- PSI</div>
            <div class="sensor-chart-container">
                <canvas id="sensor-chart-${sensor.id}"></canvas>
            </div>
        </div>
    `;
}

/**
 * Initializes Chart.js chart for a sensor
 */
function initSensorChart(sensorId, index) {
    const ctx = document.getElementById(`sensor-chart-${sensorId}`);
    if (!ctx) return;
    
    const colorIndex = index % CHART_COLORS.length;
    
    State.sensorHistory[sensorId] = [];
    
    State.sensorCharts[sensorId] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                data: [],
                borderColor: CHART_COLORS[colorIndex],
                backgroundColor: `${CHART_COLORS[colorIndex]}20`,
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    display: false
                },
                y: {
                    display: true,
                    grid: {
                        color: '#333',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#666',
                        font: { size: 10 },
                        maxTicksLimit: 3
                    }
                }
            }
        }
    });
}

/**
 * Renders all sensor cards and initializes charts
 */
function renderSensors() {
    const container = document.getElementById('sensors-container');
    
    if (State.sensors.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📊</div>
                <p>No pressure sensors configured</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = State.sensors.map((sensor, i) => createSensorCard(sensor, i)).join('');
    
    State.sensors.forEach((sensor, i) => {
        initSensorChart(sensor.id, i);
    });
}

/**
 * Updates sensor value display and chart
 */
function updateSensorDisplay(sensorId, pressure) {
    const valueEl = document.getElementById(`sensor-value-${sensorId}`);
    if (valueEl) {
        valueEl.textContent = `${pressure.toFixed(1)} PSI`;
    }
    
    const history = State.sensorHistory[sensorId];
    if (history) {
        history.push(pressure);
        if (history.length > CHART_MAX_POINTS) {
            history.shift();
        }
        
        const chart = State.sensorCharts[sensorId];
        if (chart) {
            chart.data.labels = history.map((_, i) => i);
            chart.data.datasets[0].data = history;
            chart.update('none');
        }
    }
}

/**
 * Polls sensor data from server
 */
async function pollSensors() {
    try {
        const sensors = await API.getSensorInfo();
        State.sensors = sensors;
        
        sensors.forEach(sensor => {
            updateSensorDisplay(sensor.id, sensor.current_pressure);
        });
        
        updateAllStepRequirements();
    } catch (error) {
        logError('Failed to poll sensor data', error);
    }
}

/**
 * Sensor polling loop
 */
async function sensorPollingLoop() {
    if (State.connected) {
        await pollSensors();
    }
    setTimeout(sensorPollingLoop, SENSOR_POLL_INTERVAL);
}

/**
 * Toggles safe mode on/off
 */
async function toggleSafeMode() {
    const newState = !State.safeMode;
    
    try {
        await API.setSafeMode(newState);
        State.safeMode = newState;
        updateSafeModeUI();
        logStatus(`Safe mode ${newState ? 'enabled' : 'disabled'}`);
    } catch (error) {
        logError('Failed to toggle safe mode', error);
        Modal.show('Error', `<p>Failed to toggle safe mode: ${error.message}</p>`, [
            { label: 'OK', type: 'primary' }
        ]);
    }
}

/**
 * Updates safe mode button UI
 */
function updateSafeModeUI() {
    const btn = document.getElementById('safe-mode-btn');
    const text = btn.querySelector('.safe-mode-text');
    
    if (State.safeMode) {
        btn.classList.add('active');
        text.textContent = 'Safe Mode: ON';
    } else {
        btn.classList.remove('active');
        text.textContent = 'Safe Mode: OFF';
    }
}

/**
 * Polls safe mode status from server
 */
async function pollSafeMode() {
    try {
        const response = await API.getSafeMode();
        State.safeMode = response.safe_mode;
        updateSafeModeUI();
    } catch (error) {
        logError('Failed to poll safe mode', error);
    }
}

/**
 * Safe mode polling loop
 */
async function safeModePollingLoop() {
    if (State.connected) {
        await pollSafeMode();
    }
    setTimeout(safeModePollingLoop, SAFE_MODE_POLL_INTERVAL);
}

/**
 * Populates procedure selector dropdown
 */
function initProcedures() {
    const select = document.getElementById('procedure-select');
    const procedures = CONFIG.procedures || [];
    
    if (procedures.length === 0) {
        select.innerHTML = '<option value="">No procedures configured</option>';
        return;
    }
    
    select.innerHTML = procedures.map((proc, i) => 
        `<option value="${i}">${proc.name}</option>`
    ).join('');
    
    selectProcedure();
}

/**
 * Handles procedure selection change
 */
function selectProcedure() {
    const select = document.getElementById('procedure-select');
    const index = parseInt(select.value);
    
    if (isNaN(index) || !CONFIG.procedures[index]) {
        State.selectedProcedure = null;
        document.getElementById('procedure-steps').innerHTML = '';
        return;
    }
    
    State.selectedProcedure = CONFIG.procedures[index];
    State.completedSteps.clear();
    renderProcedureSteps();
}

/**
 * Formats a requirement for display
 */
function formatRequirement(req) {
    switch (req.type) {
        case 'pressure_below':
            return `Sensor ${req.sensor_id} pressure below ${req.threshold} PSI`;
        case 'pressure_above':
            return `Sensor ${req.sensor_id} pressure above ${req.threshold} PSI`;
        case 'pressure_between':
            return `Sensor ${req.sensor_id} pressure between ${req.min_threshold} and ${req.max_threshold} PSI`;
        case 'valve_state':
            return `Valve ${req.valve_id} is ${req.state}`;
        default:
            return JSON.stringify(req);
    }
}

/**
 * Formats an action for display
 */
function formatAction(action) {
    switch (action.type) {
        case 'set_valve':
            return `Set valve ${action.valve_id} to ${action.state}`;
        case 'wait':
            return `Wait ${action.duration} seconds`;
        case 'user_confirm':
            return `User confirmation: "${action.message}"`;
        default:
            return JSON.stringify(action);
    }
}

/**
 * Checks if a single requirement is met
 */
function checkRequirementMet(req) {
    switch (req.type) {
        case 'pressure_below': {
            const sensor = State.sensors.find(s => s.id === req.sensor_id);
            return sensor && sensor.current_pressure < req.threshold;
        }
        case 'pressure_above': {
            const sensor = State.sensors.find(s => s.id === req.sensor_id);
            return sensor && sensor.current_pressure > req.threshold;
        }
        case 'pressure_between': {
            const sensor = State.sensors.find(s => s.id === req.sensor_id);
            return sensor && sensor.current_pressure >= req.min_threshold && sensor.current_pressure <= req.max_threshold;
        }
        case 'valve_state': {
            const valve = State.valves.find(v => v.id === req.valve_id);
            return valve && valve.current_state === req.state;
        }
        default:
            return false;
    }
}

/**
 * Checks all requirements for a step
 * @returns Object with met (boolean) and unmet (array of unmet requirement descriptions)
 */
function checkStepRequirements(step) {
    const requirements = step.requirements || [];
    const unmet = [];
    
    requirements.forEach(req => {
        if (!checkRequirementMet(req)) {
            unmet.push(formatRequirement(req));
        }
    });
    
    return {
        met: unmet.length === 0,
        unmet
    };
}

/**
 * Updates requirement indicators for all steps
 */
function updateAllStepRequirements() {
    if (!State.selectedProcedure) return;
    
    State.selectedProcedure.steps.forEach((step, index) => {
        const result = checkStepRequirements(step);
        State.currentRequirementsMet[index] = result;
        
        const indicator = document.querySelector(`.step-card[data-step-index="${index}"] .requirements-indicator`);
        if (indicator) {
            if (result.met) {
                indicator.classList.add('met');
            } else {
                indicator.classList.remove('met');
            }
        }
        
        const requirements = step.requirements || [];
        requirements.forEach((req, reqIndex) => {
            const reqStatus = document.querySelector(
                `.step-card[data-step-index="${index}"] .requirement-item[data-req-index="${reqIndex}"] .requirement-status`
            );
            if (reqStatus) {
                if (checkRequirementMet(req)) {
                    reqStatus.classList.add('met');
                } else {
                    reqStatus.classList.remove('met');
                }
            }
        });
    });
}

/**
 * Creates step card HTML
 */
function createStepCard(step, index) {
    const isCompleted = State.completedSteps.has(index);
    const requirements = step.requirements || [];
    const actions = step.actions || [];
    const reqResult = checkStepRequirements(step);
    
    State.currentRequirementsMet[index] = reqResult;
    
    return `
        <div class="step-card ${isCompleted ? 'completed' : ''}" data-step-index="${index}">
            <div class="step-header" onclick="toggleStepExpand(${index})">
                <div class="step-info">
                    <span class="step-number">${isCompleted ? '✓' : index + 1}</span>
                    <span class="step-name">${step.name}</span>
                </div>
                <div class="step-status">
                    <span class="requirements-indicator ${reqResult.met ? 'met' : ''}" 
                          title="${reqResult.met ? 'Requirements met' : 'Requirements not met'}"></span>
                    <span class="step-toggle">▼</span>
                </div>
            </div>
            <div class="step-details">
                ${requirements.length > 0 ? `
                    <div class="step-section">
                        <div class="step-section-title">Requirements</div>
                        <div class="step-section-content">
                            <ul>
                                ${requirements.map((req, reqIndex) => `
                                    <li class="requirement-item" data-req-index="${reqIndex}">
                                        <span class="requirement-status ${checkRequirementMet(req) ? 'met' : ''}"></span>
                                        ${formatRequirement(req)}
                                    </li>
                                `).join('')}
                            </ul>
                        </div>
                    </div>
                ` : ''}
                ${actions.length > 0 ? `
                    <div class="step-section">
                        <div class="step-section-title">Actions</div>
                        <div class="step-section-content">
                            <ul>
                                ${actions.map(action => `<li>${formatAction(action)}</li>`).join('')}
                            </ul>
                        </div>
                    </div>
                ` : ''}
                <button class="step-execute-btn" onclick="executeStep(${index}, event)">
                    ${isCompleted ? 'Execute Again' : 'Execute Step'}
                </button>
            </div>
        </div>
    `;
}

/**
 * Renders all procedure steps
 */
function renderProcedureSteps() {
    const container = document.getElementById('procedure-steps');
    
    if (!State.selectedProcedure) {
        container.innerHTML = '';
        return;
    }
    
    const steps = State.selectedProcedure.steps || [];
    
    if (steps.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📋</div>
                <p>No steps in this procedure</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = steps.map((step, i) => createStepCard(step, i)).join('');
}

/**
 * Toggles step card expansion
 */
function toggleStepExpand(index) {
    const card = document.querySelector(`.step-card[data-step-index="${index}"]`);
    if (card) {
        card.classList.toggle('expanded');
    }
}

/**
 * Gets the expected next step index in sequence
 */
function getExpectedNextStep() {
    if (!State.selectedProcedure) return 0;
    
    for (let i = 0; i < State.selectedProcedure.steps.length; i++) {
        if (!State.completedSteps.has(i)) {
            return i;
        }
    }
    return State.selectedProcedure.steps.length;
}

/**
 * Executes a procedure step with validation
 */
async function executeStep(index, event) {
    if (event) event.stopPropagation();
    
    if (!State.selectedProcedure) return;
    
    const step = State.selectedProcedure.steps[index];
    const isCompleted = State.completedSteps.has(index);
    const expectedNext = getExpectedNextStep();
    const isOutOfOrder = index !== expectedNext && !isCompleted;
    
    const warnings = [];
    
    if (isCompleted) {
        warnings.push('This step has already been completed.');
    }
    
    if (isOutOfOrder) {
        warnings.push(`This step is out of order. Expected step ${expectedNext + 1} next.`);
    }
    
    const reqResult = State.currentRequirementsMet[index] || checkStepRequirements(step);
    if (!reqResult.met) {
        warnings.push('Requirements not met:');
        reqResult.unmet.forEach(u => warnings.push(`• ${u}`));
    }
    
    if (warnings.length > 0) {
        Modal.warning(
            'Step Execution Warning',
            `<p>The following issues were detected:</p>
            <ul>${warnings.map(w => `<li>${w}</li>`).join('')}</ul>
            <p>Do you want to proceed anyway?</p>`,
            () => performStepExecution(index, step)
        );
    } else {
        performStepExecution(index, step);
    }
}

/**
 * Performs the actual step execution
 */
async function performStepExecution(index, step) {
    logStatus(`Executing step ${index + 1}: ${step.name}`);
    
    const actions = step.actions || [];
    
    for (const action of actions) {
        try {
            await executeAction(action);
        } catch (error) {
            logError(`Action failed: ${action.type}`, error);
            Modal.show('Action Failed', `<p>Failed to execute action: ${error.message}</p>`, [
                { label: 'OK', type: 'primary' }
            ]);
            return;
        }
    }
    
    State.completedSteps.add(index);
    renderProcedureSteps();
    logStatus(`Step ${index + 1} completed: ${step.name}`);
}

/**
 * Executes a single action
 * @returns Promise that resolves when action completes
 */
async function executeAction(action) {
    switch (action.type) {
        case 'set_valve':
            await API.setValveStates({ [action.valve_id]: action.state });
            await pollValves();
            break;
            
        case 'wait':
            await new Promise(resolve => setTimeout(resolve, action.duration * 1000));
            break;
            
        case 'user_confirm':
            await new Promise((resolve, reject) => {
                Modal.show(
                    'Confirmation Required',
                    `<p>${action.message}</p>`,
                    [
                        { label: 'Cancel', type: 'secondary', callback: () => reject(new Error('User cancelled')) },
                        { label: 'Confirm', type: 'primary', callback: resolve }
                    ]
                );
            });
            break;
            
        default:
            logError(`Unknown action type: ${action.type}`);
    }
}

/**
 * Initial data load
 */
async function initialLoad() {
    try {
        const [valves, sensors] = await Promise.all([
            API.getValveInfo(),
            API.getSensorInfo()
        ]);
        
        State.valves = valves;
        State.sensors = sensors;
        
        renderValves();
        renderSensors();
        initProcedures();
        
        await pollSafeMode();
        
        logStatus('Initial data loaded successfully');
    } catch (error) {
        logError('Failed to load initial data', error);
    }
}

/**
 * Application initialization
 */
async function init() {
    logStatus('Ground Control System initializing...');
    
    try {
        await API.sendHeartbeat();
        updateConnectionStatus(true);
    } catch {
        updateConnectionStatus(false);
    }
    
    await initialLoad();
    
    heartbeatLoop();
    valvePollingLoop();
    sensorPollingLoop();
    safeModePollingLoop();
    
    logStatus('Ground Control System initialized');
}

document.addEventListener('DOMContentLoaded', init);
