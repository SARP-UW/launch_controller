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
    selectedProcedureIndex: 0,
    completedSteps: new Set(),
    currentRequirementsMet: {},
    pulsingValves: new Set() // Track which valves are currently pulsing
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
    },

    async pulseValves(pulses) {
        return this.request('/api/pulse_valves', {
            method: 'POST',
            body: JSON.stringify(pulses)
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
    const isPulsing = State.pulsingValves.has(valve.id);
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
            <button class="valve-btn pulse-btn ${isPulsing ? 'pulsing' : ''}" 
                    onclick="pulseValve(${valve.id})"
                    ${isPulsing ? 'disabled' : ''}>
                <div class="pulse-progress" data-valve-id="${valve.id}"></div>
                <span class="pulse-label">Pulse</span>
                <input type="number" 
                       class="pulse-duration-input" 
                       data-valve-id="${valve.id}"
                       placeholder="1.0" 
                       min="0.1" 
                       step="0.1" 
                       value="1.0"
                       ${isPulsing ? 'disabled' : ''}
                       onclick="event.stopPropagation()"
                       onmousedown="event.stopPropagation()">
            </button>
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
        const valveName = valve ? `${valve.name} (${valveId})` : `Valve ${valveId}`;
        
        Modal.warning(
            'Invalid Valve Configuration',
            `<p>Setting <strong>${valveName}</strong> to <strong>${state}</strong> will result in an invalid configuration.</p>`,
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
 * Pulses a valve for the specified duration
 */
async function pulseValve(valveId) {
    // Prevent multiple pulses on the same valve
    if (State.pulsingValves.has(valveId)) {
        logError(`Valve ${valveId} is already pulsing`);
        return;
    }

    const input = document.querySelector(`.pulse-duration-input[data-valve-id="${valveId}"]`);
    const duration = parseFloat(input?.value) || 1.0;

    if (duration <= 0) {
        Modal.show('Invalid Duration', '<p>Pulse duration must be greater than 0.</p>', [
            { label: 'OK', type: 'primary' }
        ]);
        return;
    }

    // Check for invalid state warnings (similar to setValveState)
    const valve = State.valves.find(v => v.id === valveId);
    const newState = valve?.current_state === 'open' ? 'closed' : 'open';
    const violations = checkInvalidValveState(valveId, newState);

    if (violations.length > 0) {
        const valveName = valve ? valve.name : `Valve ${valveId}`;
        Modal.warning(
            'Invalid Valve Configuration',
            `<p>Pulsing <strong>${valveName}</strong> would result in an invalid configuration:</p>
            <ul>${violations.map(v => `<li>${v}</li>`).join('')}</ul>`,
            () => executePulse(valveId, duration)
        );
        return;
    }

    executePulse(valveId, duration);
}

/**
 * Executes the pulse operation with visual feedback
 */
async function executePulse(valveId, duration) {
    // Mark valve as pulsing
    State.pulsingValves.add(valveId);
    updatePulseUI(valveId, true, duration);

    try {
        // Start the pulse on the server
        const response = await API.pulseValves({ [valveId]: duration });
        
        if (response.status === 'error' && response.failed_valves) {
            throw new Error(response.failed_valves[valveId] || 'Unknown error');
        }

        logStatus(`Valve ${valveId} pulse started for ${duration}s`);

        // Wait for pulse duration (progress animation runs independently)
        await new Promise(resolve => setTimeout(resolve, duration * 1000));

        logStatus(`Valve ${valveId} pulse completed`);
    } catch (error) {
        logError(`Failed to pulse valve ${valveId}`, error);
        Modal.show('Pulse Failed', `<p>Failed to pulse valve: ${error.message}</p>`, [
            { label: 'OK', type: 'primary' }
        ]);
    } finally {
        // Mark valve as no longer pulsing
        State.pulsingValves.delete(valveId);
        updatePulseUI(valveId, false, 0);
        await pollValves(); // Refresh valve state
    }
}

/**
 * Updates the pulse UI elements for a valve
 */
function updatePulseUI(valveId, isPulsing, duration) {
    const card = document.querySelector(`.valve-card[data-valve-id="${valveId}"]`);
    if (!card) return;

    const input = card.querySelector('.pulse-duration-input');
    const button = card.querySelector('.pulse-btn');
    const progress = card.querySelector('.pulse-progress');

    if (isPulsing) {
        input.disabled = true;
        button.classList.add('pulsing');
        button.disabled = true;

        // Start progress animation
        progress.style.transition = 'none';
        progress.style.width = '100%';
        // Force reflow
        progress.offsetHeight;
        progress.style.transition = `width ${duration}s linear`;
        progress.style.width = '0%';
    } else {
        input.disabled = false;
        button.classList.remove('pulsing');
        button.disabled = false;

        // Reset progress bar
        progress.style.transition = 'none';
        progress.style.width = '0%';
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
            <div class="sensor-data-row">
                <div class="sensor-data-panel">
                    <div class="sensor-data-label">Pressure</div>
                    <div class="sensor-data-value" id="sensor-value-${sensor.id}">-- PSI</div>
                </div>
                <div class="sensor-data-panel">
                    <div class="sensor-data-label">Rate</div>
                    <div class="sensor-data-value sensor-rate" id="sensor-rate-${sensor.id}">-- PSI/s</div>
                </div>
            </div>
            <div class="sensor-chart-panel">
                <div class="sensor-chart-container">
                    <canvas id="sensor-chart-${sensor.id}"></canvas>
                </div>
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
        // Calculate rate of change using average over last several readings
        const rateEl = document.getElementById(`sensor-rate-${sensorId}`);
        if (rateEl && history.length >= 10) {
            // Use readings from 10 samples ago for more stable rate calculation
            const sampleWindow = 10;
            const oldPressure = history[history.length - sampleWindow];
            const timeDelta = (sampleWindow * SENSOR_POLL_INTERVAL) / 1000; // Convert to seconds
            const rate = (pressure - oldPressure) / timeDelta;
            const rateStr = rate >= 0 ? `+${rate.toFixed(1)}` : rate.toFixed(1);
            rateEl.textContent = `${rateStr} PSI/s`;
            rateEl.classList.toggle('positive', rate > 0.5);
            rateEl.classList.toggle('negative', rate < -0.5);
        } else if (rateEl) {
            rateEl.textContent = '-- PSI/s';
        }
        
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
    const selector = document.getElementById('procedure-selector');
    const btn = document.getElementById('procedure-dropdown-btn');
    const menu = document.getElementById('procedure-dropdown-menu');
    const procedures = CONFIG.procedures || [];
    
    if (procedures.length === 0) {
        btn.textContent = 'No procedures configured';
        btn.disabled = true;
        return;
    }
    
    // Populate dropdown menu
    menu.innerHTML = procedures.map((proc, i) => 
        `<div class="procedure-dropdown-item" data-index="${i}">${proc.name}</div>`
    ).join('');
    
    // Set initial selection
    btn.textContent = procedures[0].name;
    menu.querySelector('.procedure-dropdown-item').classList.add('selected');
    
    // Toggle dropdown on button click
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        selector.classList.toggle('open');
    });
    
    // Handle item selection
    menu.addEventListener('click', (e) => {
        const item = e.target.closest('.procedure-dropdown-item');
        if (item) {
            const index = parseInt(item.dataset.index);
            btn.textContent = item.textContent;
            
            // Update selected state
            menu.querySelectorAll('.procedure-dropdown-item').forEach(el => el.classList.remove('selected'));
            item.classList.add('selected');
            
            selector.classList.remove('open');
            selectProcedure(index);
        }
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!selector.contains(e.target)) {
            selector.classList.remove('open');
        }
    });
    
    selectProcedure(0);
}

/**
 * Handles procedure selection change
 */
function selectProcedure(index) {
    if (typeof index !== 'number' || isNaN(index) || !CONFIG.procedures[index]) {
        State.selectedProcedure = null;
        document.getElementById('procedure-steps').innerHTML = '';
        return;
    }
    
    State.selectedProcedure = CONFIG.procedures[index];
    State.selectedProcedureIndex = index;
    State.completedSteps.clear();
    renderProcedureSteps();
}

/**
 * Gets sensor name with ID in parenthesis
 */
function getSensorLabel(sensorId) {
    const sensor = State.sensors.find(s => s.id === sensorId);
    return sensor ? `${sensor.name} (${sensorId})` : `Sensor ${sensorId}`;
}

/**
 * Gets valve name with ID in parenthesis
 */
function getValveLabel(valveId) {
    const valve = State.valves.find(v => v.id === valveId);
    return valve ? `${valve.name} (${valveId})` : `Valve ${valveId}`;
}

/**
 * Formats a requirement for display (met state - using "is")
 */
function formatRequirement(req) {
    switch (req.type) {
        case 'pressure_below':
            return `${getSensorLabel(req.sensor_id)} pressure is below ${req.threshold} PSI`;
        case 'pressure_above':
            return `${getSensorLabel(req.sensor_id)} pressure is above ${req.threshold} PSI`;
        case 'pressure_between':
            return `${getSensorLabel(req.sensor_id)} pressure is between ${req.min_threshold} and ${req.max_threshold} PSI`;
        case 'valve_state':
            return `${getValveLabel(req.valve_id)} is ${req.state}`;
        default:
            return JSON.stringify(req);
    }
}

/**
 * Formats a requirement for display when NOT met (using "is not")
 */
function formatRequirementUnmet(req) {
    switch (req.type) {
        case 'pressure_below':
            return `${getSensorLabel(req.sensor_id)} pressure is not below ${req.threshold} PSI`;
        case 'pressure_above':
            return `${getSensorLabel(req.sensor_id)} pressure is not above ${req.threshold} PSI`;
        case 'pressure_between':
            return `${getSensorLabel(req.sensor_id)} pressure is not between ${req.min_threshold} and ${req.max_threshold} PSI`;
        case 'valve_state':
            return `${getValveLabel(req.valve_id)} is not ${req.state}`;
        default:
            return JSON.stringify(req);
    }
}

/**
 * Formats an action for display
 */
function formatAction(action) {
    switch (action.type) {
        case 'set_valve': {
            const stateWord = action.state === 'open' ? 'Open' : 'Close';
            return `${stateWord} ${getValveLabel(action.valve_id)}`;
        }
        case 'pulse_valve':
            return `Pulse ${getValveLabel(action.valve_id)} for ${action.duration}s`;
        case 'wait':
            return `Wait ${action.duration} seconds`;
        case 'user_confirm':
            return `Await user confirmation: "${action.message}"`;
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
            unmet.push(formatRequirementUnmet(req));
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
                        <div class="step-section-content requirements-list">
                            ${requirements.map((req, reqIndex) => `
                                <div class="requirement-item" data-req-index="${reqIndex}">
                                    <span class="requirement-status ${checkRequirementMet(req) ? 'met' : ''}"></span>
                                    <span class="requirement-text">${formatRequirement(req)}</span>
                                </div>
                            `).join('')}
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
                <div class="step-buttons">
                    <button class="step-execute-btn" onclick="executeStep(${index}, event)">
                        ${isCompleted ? 'Execute Again' : 'Execute Step'}
                    </button>
                    <button class="step-mark-btn ${isCompleted ? 'completed' : ''}" onclick="toggleStepComplete(${index}, event)">
                        ✓
                    </button>
                </div>
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
 * Toggles a step's completion status without executing it
 */
function toggleStepComplete(index, event) {
    if (event) event.stopPropagation();
    
    if (State.completedSteps.has(index)) {
        State.completedSteps.delete(index);
        logStatus(`Step ${index + 1} marked as incomplete`);
    } else {
        State.completedSteps.add(index);
        logStatus(`Step ${index + 1} marked as complete`);
    }
    
    renderProcedureSteps();
}

/**
 * Resets all steps in the current procedure
 */
function resetProcedure() {
    if (!State.selectedProcedure) return;
    
    State.completedSteps.clear();
    renderProcedureSteps();
    logStatus('Procedure reset - all steps marked as incomplete');
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
        warnings.push('This step is out of order.');
    }
    
    const reqResult = State.currentRequirementsMet[index] || checkStepRequirements(step);
    if (!reqResult.met) {
        reqResult.unmet.forEach(u => warnings.push(u));
    }
    
    if (warnings.length > 0) {
        Modal.warning(
            'Step Execution Warning',
            `<p>The following issues were detected:</p>
            <ul>${warnings.map(w => `<li>${w}</li>`).join('')}</ul>`,
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

        case 'pulse_valve': {
            const valveId = action.valve_id;
            const duration = action.duration;

            // Check if valve is already pulsing
            if (State.pulsingValves.has(valveId)) {
                throw new Error(`Valve ${valveId} is already pulsing`);
            }

            // Mark as pulsing and update UI
            State.pulsingValves.add(valveId);
            updatePulseUI(valveId, true, duration);

            try {
                const response = await API.pulseValves({ [valveId]: duration });
                if (response.status === 'error' && response.failed_valves) {
                    throw new Error(response.failed_valves[valveId] || 'Unknown error');
                }
                // Wait for pulse to complete
                await new Promise(resolve => setTimeout(resolve, duration * 1000));
            } finally {
                State.pulsingValves.delete(valveId);
                updatePulseUI(valveId, false, 0);
                await pollValves();
            }
            break;
        }
            
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
 * Updates the procedures panel max height to match the left panel
 */
function updateProceduresPanelHeight() {
    const leftPanel = document.querySelector('.left-panel');
    const proceduresPanel = document.querySelector('.procedures-panel');
    
    if (leftPanel && proceduresPanel) {
        const leftPanelHeight = leftPanel.offsetHeight;
        const minHeight = 300;
        const maxHeight = Math.max(leftPanelHeight, minHeight);
        proceduresPanel.style.maxHeight = `${maxHeight}px`;
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
    
    // Set procedures panel height after content loads
    setTimeout(updateProceduresPanelHeight, 100);
    
    // Update on window resize
    window.addEventListener('resize', updateProceduresPanelHeight);
    
    heartbeatLoop();
    valvePollingLoop();
    sensorPollingLoop();
    safeModePollingLoop();
    
    logStatus('Ground Control System initialized');
}

document.addEventListener('DOMContentLoaded', init);
