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
const PROCEDURE_POLL_INTERVAL = 1000;

// Chart configuration
const CHART_MAX_POINTS = 100;
const CHART_COLOR = '#3b82f6';

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
    expandedSteps: new Set(),
    currentRequirementsMet: {},
    pulsingValves: new Set(), // Track which valves are currently pulsing
    executingStepIndex: null, // Track which step is currently executing
    executingStepUser: null, // Track who is executing the step (for display)
    safingSystem: false, // Track if system is being safed
    safingSystemUser: null // Track who is safing the system
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
        const overlay = document.getElementById('modal-overlay');
        const container = document.getElementById('modal-container');
        
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
        
        // Remove closing class and show
        overlay.classList.remove('closing');
        container.classList.remove('closing');
        overlay.classList.remove('hidden');
    },
    
    close() {
        const overlay = document.getElementById('modal-overlay');
        const container = document.getElementById('modal-container');
        
        // Add closing animation classes
        overlay.classList.add('closing');
        container.classList.add('closing');
        
        // Wait for animation to complete, then hide
        setTimeout(() => {
            overlay.classList.add('hidden');
            overlay.classList.remove('closing');
            container.classList.remove('closing');
        }, 200);
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
    },

    async getProcedures() {
        return this.request('/api/get_procedures');
    },

    async getInvalidValveStates() {
        return this.request('/api/get_invalid_valve_states');
    },

    async getWebsiteTitle() {
        return this.request('/api/get_website_title');
    },

    async getProcedureStatus() {
        return this.request('/api/get_procedure_status');
    },

    async isSafing() {
        return this.request('/api/is_safing');
    },

    async startStepExecution(procedureIndex, stepIndex) {
        return this.request('/api/start_step_execution', {
            method: 'POST',
            body: JSON.stringify({ procedure_index: procedureIndex, step_index: stepIndex })
        });
    },

    async setStepCompletion(procedureIndex, stepIndex, completed) {
        return this.request('/api/set_step_completion', {
            method: 'POST',
            body: JSON.stringify({ procedure_index: procedureIndex, step_index: stepIndex, completed: completed })
        });
    },

    async resetProcedure(procedureIndex) {
        return this.request('/api/reset_procedure', {
            method: 'POST',
            body: JSON.stringify({ procedure_index: procedureIndex })
        });
    },

    async safeSystem() {
        return this.request('/api/safe_system', {
            method: 'POST'
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
    // Block valve operations while executing or safing
    if (State.executingStepIndex !== null || State.safingSystem) {
        const blockingAction = State.safingSystem ? 'system is being safed' : 'a step is executing';
        const blockingUser = State.safingSystem ? State.safingSystemUser : State.executingStepUser;
        const userInfo = blockingUser ? ` by ${blockingUser}` : '';
        Modal.show(
            'Operation Blocked',
            `<p>Cannot modify valves while ${blockingAction}${userInfo}. Please wait for it to complete.</p>`,
            [{ label: 'OK', type: 'primary' }]
        );
        return;
    }
    
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
            { label: 'OK', type: 'secondary' }
        ]);
    }
}

/**
 * Pulses a valve for the specified duration
 */
async function pulseValve(valveId) {
    // Block valve operations while executing or safing
    if (State.executingStepIndex !== null || State.safingSystem) {
        const blockingAction = State.safingSystem ? 'system is being safed' : 'a step is executing';
        const blockingUser = State.safingSystem ? State.safingSystemUser : State.executingStepUser;
        const userInfo = blockingUser ? ` by ${blockingUser}` : '';
        Modal.show(
            'Operation Blocked',
            `<p>Cannot pulse valves while ${blockingAction}${userInfo}. Please wait for it to complete.</p>`,
            [{ label: 'OK', type: 'primary' }]
        );
        return;
    }
    
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

        // Only show progress animation for durations >= 0.2s
        if (duration >= 0.2) {
            progress.style.transition = 'none';
            progress.style.width = '100%';
            // Force reflow
            progress.offsetHeight;
            progress.style.transition = `width ${duration}s linear`;
            progress.style.width = '0%';
        }
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
                <div class="sensor-data-panel sensor-rate-panel">
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
    
    State.sensorHistory[sensorId] = [];
    
    State.sensorCharts[sensorId] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                data: [],
                borderColor: CHART_COLOR,
                backgroundColor: `${CHART_COLOR}20`,
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4,
                pointHoverBackgroundColor: CHART_COLOR,
                pointHoverBorderColor: '#fff',
                pointHoverBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    enabled: true,
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(30, 30, 30, 0.9)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderColor: '#444',
                    borderWidth: 1,
                    padding: 8,
                    displayColors: false,
                    callbacks: {
                        title: function() {
                            return '';
                        },
                        label: function(context) {
                            const pressure = context.parsed.y;
                            const dataIndex = context.dataIndex;
                            const history = State.sensorHistory[sensorId];
                            if (history && history[dataIndex]) {
                                const secondsAgo = ((Date.now() - history[dataIndex].time) / 1000).toFixed(1);
                                return [`${pressure.toFixed(1)} PSI`, `${secondsAgo}s ago`];
                            }
                            return [`${pressure.toFixed(1)} PSI`];
                        }
                    }
                }
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
        const now = Date.now();
        
        // Calculate rate of change using average over last several readings
        const rateEl = document.getElementById(`sensor-rate-${sensorId}`);
        if (rateEl && history.length >= 10) {
            // Use readings from 10 samples ago for more stable rate calculation
            const sampleWindow = 10;
            const oldEntry = history[history.length - sampleWindow];
            const timeDelta = (now - oldEntry.time) / 1000; // Convert to seconds
            const rate = (pressure - oldEntry.pressure) / timeDelta;
            const rateStr = rate >= 0 ? `+${rate.toFixed(1)}` : rate.toFixed(1);
            rateEl.textContent = `${rateStr} PSI/s`;
            rateEl.classList.toggle('positive', rate > 0.5);
            rateEl.classList.toggle('negative', rate < -0.5);
        } else if (rateEl) {
            rateEl.textContent = '-- PSI/s';
        }
        
        history.push({ time: now, pressure: pressure });
        if (history.length > CHART_MAX_POINTS) {
            history.shift();
        }
        
        const chart = State.sensorCharts[sensorId];
        if (chart) {
            chart.data.labels = history.map((_, i) => i);
            chart.data.datasets[0].data = history.map(entry => entry.pressure);
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
            { label: 'OK', type: 'secondary' }
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
 * Triggers manual safe system operation
 */
async function safeSystem() {
    // Block if already safing or executing
    if (State.safingSystem) {
        const userInfo = State.safingSystemUser ? ` by ${State.safingSystemUser}` : '';
        Modal.show(
            'System Already Safing',
            `<p>The system is already being safed${userInfo}. Please wait for it to complete.</p>`,
            [{ label: 'OK', type: 'primary' }]
        );
        return;
    }
    
    if (State.executingStepIndex !== null) {
        const userInfo = State.executingStepUser ? ` by ${State.executingStepUser}` : '';
        Modal.show(
            'Step Executing',
            `<p>A step is currently executing${userInfo}. Please wait for it to complete before safing the system.</p>`,
            [{ label: 'OK', type: 'primary' }]
        );
        return;
    }
    
    // Confirmation dialog
    const confirmed = await new Promise(resolve => {
        Modal.show(
            'Confirm Safe System',
            '<p>Are you sure you want to safe the system? This will close all valves to their safe states.</p>',
            [
                { label: 'Cancel', type: 'secondary', action: () => resolve(false) },
                { label: 'Safe System', type: 'primary', action: () => resolve(true) }
            ]
        );
    });
    
    if (!confirmed) return;
    
    try {
        const result = await API.safeSystem();
        if (result.status === 'success') {
            logStatus('Safe system initiated');
            // The polling will update the UI state
        } else {
            throw new Error(result.message || 'Failed to initiate safe system');
        }
    } catch (error) {
        logError('Failed to safe system', error);
        Modal.show('Error', `<p>Failed to safe system: ${error.message}</p>`, [
            { label: 'OK', type: 'secondary' }
        ]);
    }
}

/**
 * Updates safe system button UI
 */
function updateSafeSystemUI() {
    const btn = document.getElementById('safe-system-btn');
    if (!btn) return;
    
    if (State.safingSystem) {
        btn.classList.add('executing');
        btn.disabled = true;
        btn.innerHTML = '<span class="safe-system-text">Safing...</span>';
    } else {
        btn.classList.remove('executing');
        btn.disabled = State.executingStepIndex !== null;
        btn.innerHTML = '<span class="safe-system-text">Safe System</span>';
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
 * Polls procedures from server and updates if changed
 */
async function pollProcedures() {
    try {
        const procedures = await API.getProcedures();
        
        // Check if procedures have changed by comparing JSON
        const currentJson = JSON.stringify(CONFIG.procedures);
        const newJson = JSON.stringify(procedures);
        
        if (currentJson !== newJson) {
            logStatus('Procedures updated from server');
            CONFIG.procedures = procedures;
            
            // Reset procedure state
            State.completedSteps.clear();
            State.expandedSteps.clear();
            State.selectedProcedure = null;
            State.selectedProcedureIndex = 0;
            
            // Reinitialize procedures UI
            initProcedures();
        }
    } catch (error) {
        logError('Failed to poll procedures', error);
    }
}

/**
 * Procedure polling loop - polls for procedure definition changes
 */
async function procedurePollingLoop() {
    if (State.connected && State.executingStepIndex === null) {
        await pollProcedures();
    }
    setTimeout(procedurePollingLoop, PROCEDURE_POLL_INTERVAL);
}

// Polling interval for procedure status (completion and execution state)
const PROCEDURE_STATUS_POLL_INTERVAL = 250;

/**
 * Polls procedure status (completion and execution state) from server
 */
async function pollProcedureStatus() {
    try {
        const status = await API.getProcedureStatus();
        
        let needsRender = false;
        
        // Update completion state for current procedure
        const currentProcIndex = State.selectedProcedureIndex;
        const serverCompleted = new Set(status.completion[currentProcIndex] || []);
        
        // Check if completion state changed
        if (serverCompleted.size !== State.completedSteps.size ||
            [...serverCompleted].some(i => !State.completedSteps.has(i))) {
            State.completedSteps = serverCompleted;
            needsRender = true;
        }
        
        // Update execution state
        const executing = status.executing;
        const wasExecuting = State.executingStepIndex;
        if (executing && executing.procedure_index === currentProcIndex) {
            // A step is executing in the current procedure
            if (State.executingStepIndex !== executing.step_index ||
                State.executingStepUser !== executing.user) {
                State.executingStepIndex = executing.step_index;
                State.executingStepUser = executing.user;
                needsRender = true;
            }
        } else {
            // No step executing in current procedure
            if (State.executingStepIndex !== null) {
                State.executingStepIndex = null;
                State.executingStepUser = null;
                needsRender = true;
            }
        }
        
        // Update safe system button UI when execution state changes
        if (wasExecuting !== State.executingStepIndex) {
            updateSafeSystemUI();
        }
        
        if (needsRender) {
            renderProcedureSteps();
        }
    } catch (error) {
        logError('Failed to poll procedure status', error);
    }
}

/**
 * Polls safing status from server
 */
async function pollSafingStatus() {
    try {
        const status = await API.isSafing();
        
        const wasSafing = State.safingSystem;
        if (status.safing) {
            State.safingSystem = true;
            State.safingSystemUser = status.user;
        } else {
            State.safingSystem = false;
            State.safingSystemUser = null;
        }
        
        // Update UI when safing state changes
        if (wasSafing !== State.safingSystem) {
            updateSafeSystemUI();
            renderProcedureSteps();
        }
    } catch (error) {
        logError('Failed to poll safing status', error);
    }
}

/**
 * Procedure status polling loop
 */
async function procedureStatusPollingLoop() {
    if (State.connected) {
        await pollProcedureStatus();
    }
    setTimeout(procedureStatusPollingLoop, PROCEDURE_STATUS_POLL_INTERVAL);
}

/**
 * Safing status polling loop
 */
async function safingStatusPollingLoop() {
    if (State.connected) {
        await pollSafingStatus();
    }
    setTimeout(safingStatusPollingLoop, PROCEDURE_STATUS_POLL_INTERVAL);
}

// Track if procedures have been initialized to avoid duplicate event listeners
let proceduresInitialized = false;

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
        menu.innerHTML = '';
        document.getElementById('procedure-steps').innerHTML = '';
        return;
    }
    
    // Enable button in case it was disabled
    btn.disabled = false;
    
    // Populate dropdown menu
    menu.innerHTML = procedures.map((proc, i) => 
        `<div class="procedure-dropdown-item" data-index="${i}">${proc.name}</div>`
    ).join('');
    
    // Set initial selection
    btn.textContent = procedures[0].name;
    const firstItem = menu.querySelector('.procedure-dropdown-item');
    if (firstItem) {
        firstItem.classList.add('selected');
    }
    
    // Only add event listeners once
    if (!proceduresInitialized) {
        proceduresInitialized = true;
        
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
    }
    
    selectProcedure(0);
}

/**
 * Handles procedure selection change
 */
async function selectProcedure(index) {
    if (typeof index !== 'number' || isNaN(index) || !CONFIG.procedures[index]) {
        State.selectedProcedure = null;
        document.getElementById('procedure-steps').innerHTML = '';
        return;
    }
    
    State.selectedProcedure = CONFIG.procedures[index];
    State.selectedProcedureIndex = index;
    State.completedSteps.clear();
    State.expandedSteps.clear(); // Clear expanded steps when changing procedures
    State.executingStepIndex = null;
    State.executingStepUser = null;
    renderProcedureSteps();
    
    // Fetch completion state from server for the newly selected procedure
    try {
        const status = await API.getProcedureStatus();
        const serverCompleted = status.completion[index] || [];
        State.completedSteps = new Set(serverCompleted);
        
        // Check if a step is executing in this procedure
        if (status.executing && status.executing.procedure_index === index) {
            State.executingStepIndex = status.executing.step_index;
            State.executingStepUser = status.executing.user;
        }
        
        renderProcedureSteps();
    } catch (error) {
        logError('Failed to fetch procedure status on selection', error);
    }
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
        case 'custom_message':
            return req.message;
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
        case 'custom_message':
            return req.message;
        default:
            return JSON.stringify(req);
    }
}

/**
 * Formats a single action for display
 */
function formatSingleAction(action) {
    switch (action.type) {
        case 'set_valve': {
            const stateWord = action.state === 'open' ? 'open' : 'close';
            return `${stateWord} ${getValveLabel(action.valve_id)}`;
        }
        case 'pulse_valve':
            return `pulse ${getValveLabel(action.valve_id)} for ${action.duration}s`;
        case 'wait':
            return `wait ${action.duration} seconds`;
        default:
            return JSON.stringify(action);
    }
}

/**
 * Formats an action or combined actions for display
 */
function formatAction(action) {
    // Handle combined actions (array)
    if (Array.isArray(action)) {
        if (action.length === 0) return '';
        if (action.length === 1) {
            const text = formatSingleAction(action[0]);
            return text.charAt(0).toUpperCase() + text.slice(1);
        }
        
        // Format as "Action1, action2, and action3"
        const formattedActions = action.map(a => formatSingleAction(a));
        const lastAction = formattedActions.pop();
        const firstAction = formattedActions.shift();
        const capitalizedFirst = firstAction.charAt(0).toUpperCase() + firstAction.slice(1);
        
        if (formattedActions.length === 0) {
            return `${capitalizedFirst} and ${lastAction}`;
        }
        return `${capitalizedFirst}, ${formattedActions.join(', ')}, and ${lastAction}`;
    }
    
    // Handle single action
    const text = formatSingleAction(action);
    return text.charAt(0).toUpperCase() + text.slice(1);
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
        case 'custom_message':
            return null; // Neutral - not evaluated
        default:
            return false;
    }
}

/**
 * Checks all requirements for a step
 * @returns Object with met (boolean), partial (boolean), and unmet (array of unmet requirement descriptions)
 */
function checkStepRequirements(step) {
    const requirements = step.requirements || [];
    const unmet = [];
    let metCount = 0;
    let evaluatableCount = 0;
    
    requirements.forEach(req => {
        // Skip custom_message requirements - they don't affect step status
        if (req.type === 'custom_message') {
            return;
        }
        
        evaluatableCount++;
        if (checkRequirementMet(req)) {
            metCount++;
        } else {
            unmet.push(formatRequirementUnmet(req));
        }
    });
    
    const partial = evaluatableCount > 0 && metCount > evaluatableCount / 2 && metCount < evaluatableCount;
    
    return {
        met: unmet.length === 0,
        partial,
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
        
        // Update step card left border color
        const card = document.querySelector(`.step-card[data-step-index="${index}"]`);
        if (card) {
            card.classList.remove('requirements-met');
            if (result.met) {
                card.classList.add('requirements-met');
            }
        }
        
        const requirements = step.requirements || [];
        requirements.forEach((req, reqIndex) => {
            const reqStatus = document.querySelector(
                `.step-card[data-step-index="${index}"] .requirement-item[data-req-index="${reqIndex}"] .requirement-status`
            );
            if (reqStatus) {
                // Skip custom_message - they always stay neutral
                if (req.type === 'custom_message') {
                    return;
                }
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
    
    // Determine requirement class for left border indicator
    let reqClass = '';
    let indicatorTitle = 'Requirements not met';
    if (reqResult.met) {
        reqClass = 'requirements-met';
        indicatorTitle = 'Requirements met';
    }
    
    // Check if this step is currently executing
    const isExecuting = State.executingStepIndex === index;
    
    if (isExecuting) {
        reqClass = 'executing';
        indicatorTitle = State.executingStepUser 
            ? `Step executing by ${State.executingStepUser}`
            : 'Step executing';
    }
    
    const isExpanded = State.expandedSteps.has(index);
    
    // Determine execute button text
    let executeButtonText = 'Execute Step';
    let executeButtonDisabled = false;
    if (isExecuting) {
        executeButtonText = State.executingStepUser 
            ? `Executing (${State.executingStepUser})`
            : 'Executing...';
        executeButtonDisabled = true;
    } else if (State.executingStepIndex !== null) {
        // Another step is executing - disable this button
        executeButtonDisabled = true;
    } else if (State.safingSystem) {
        // System is being safed - disable this button
        executeButtonDisabled = true;;
    } else if (isCompleted) {
        executeButtonText = 'Execute Again';
    }
    
    return `
        <div class="step-card ${isCompleted ? 'completed' : ''} ${isExpanded ? 'expanded' : ''} ${reqClass}" data-step-index="${index}" title="${indicatorTitle}">
            <div class="step-header" onclick="toggleStepExpand(${index})">
                <div class="step-info">
                    <span class="step-number">${isCompleted ? '✓' : index + 1}</span>
                    <span class="step-name">${step.name}</span>
                </div>
                <div class="step-status">
                    <span class="step-toggle">▼</span>
                </div>
            </div>
            <div class="step-details">
                ${requirements.length > 0 ? `
                    <div class="step-section">
                        <div class="step-section-title">Requirements</div>
                        <div class="step-section-content requirements-list">
                            ${requirements.map((req, reqIndex) => {
                                const isCustomMessage = req.type === 'custom_message';
                                const reqMet = checkRequirementMet(req);
                                let statusClass = '';
                                if (isCustomMessage) {
                                    statusClass = 'neutral';
                                } else if (reqMet) {
                                    statusClass = 'met';
                                }
                                return `
                                <div class="requirement-item" data-req-index="${reqIndex}">
                                    <span class="requirement-status ${statusClass}"></span>
                                    <span class="requirement-text">${formatRequirement(req)}</span>
                                </div>
                            `;
                            }).join('')}
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
                    <button class="step-execute-btn${isExecuting ? ' executing' : ''}" onclick="executeStep(${index}, event)"${executeButtonDisabled ? ' disabled' : ''}>
                        ${executeButtonText}
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
    
    // Fix expanded states after DOM recreation
    State.expandedSteps.forEach(index => {
        const card = document.querySelector(`.step-card[data-step-index="${index}"]`);
        if (card) {
            const details = card.querySelector('.step-details');
            if (details) {
                // Calculate and set proper height for expanded cards
                details.style.maxHeight = 'none';
                const contentHeight = details.scrollHeight;
                details.style.maxHeight = `${contentHeight + 20}px`;
            }
        }
    });
}

/**
 * Toggles step card expansion with dynamic animation duration
 */
function toggleStepExpand(index) {
    const card = document.querySelector(`.step-card[data-step-index="${index}"]`);
    if (!card) return;
    
    const details = card.querySelector('.step-details');
    const isExpanding = !State.expandedSteps.has(index);
    
    if (isExpanding) {
        // Calculate content height and dynamic duration
        details.style.maxHeight = 'none';
        const contentHeight = details.scrollHeight;
        details.style.maxHeight = '0';
        
        // Logarithmic scaling: fast for small, diminishing returns for large
        // 160ms base + log scaling to accommodate easing
        const duration = 160 + Math.log(1 + contentHeight / 50) * 35;
        details.style.setProperty('--step-duration', `${Math.round(duration)}ms`);
        
        // Force reflow then expand - add buffer for padding
        details.offsetHeight;
        details.style.maxHeight = `${contentHeight + 20}px`;
        
        State.expandedSteps.add(index);
        card.classList.add('expanded');
    } else {
        // Get current height for smooth collapse
        const currentHeight = details.scrollHeight;
        details.style.maxHeight = `${currentHeight}px`;
        
        // Logarithmic scaling for collapse (slightly faster)
        const duration = 140 + Math.log(1 + currentHeight / 50) * 30;
        details.style.setProperty('--step-duration', `${Math.round(duration)}ms`);
        
        // Force reflow then collapse
        details.offsetHeight;
        details.style.maxHeight = '0';
        
        State.expandedSteps.delete(index);
        card.classList.remove('expanded');
    }
}

/**
 * Toggles a step's completion status without executing it
 */
async function toggleStepComplete(index, event) {
    if (event) event.stopPropagation();
    
    const newCompleted = !State.completedSteps.has(index);
    
    try {
        await API.setStepCompletion(State.selectedProcedureIndex, index, newCompleted);
        
        if (newCompleted) {
            State.completedSteps.add(index);
            logStatus(`Step ${index + 1} marked as complete`);
        } else {
            State.completedSteps.delete(index);
            logStatus(`Step ${index + 1} marked as incomplete`);
        }
        
        renderProcedureSteps();
    } catch (error) {
        logError('Failed to update step completion status', error);
        Modal.show(
            'Update Failed',
            `<p>Failed to update step completion status: ${error.message}</p>`,
            [{ label: 'OK', type: 'primary' }]
        );
    }
}

/**
 * Resets all steps in the current procedure
 */
async function resetProcedure() {
    if (!State.selectedProcedure) return;
    
    try {
        await API.resetProcedure(State.selectedProcedureIndex);
        
        State.completedSteps.clear();
        // Keep expandedSteps as-is to preserve open tabs
        renderProcedureSteps();
        logStatus('Procedure reset - all steps marked as incomplete');
    } catch (error) {
        logError('Failed to reset procedure', error);
        Modal.show(
            'Reset Failed',
            `<p>Failed to reset procedure: ${error.message}</p>`,
            [{ label: 'OK', type: 'primary' }]
        );
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
 * Checks if executing a step's actions would result in any invalid valve states
 * Returns array of warning messages for invalid states that would occur
 */
function checkStepInvalidStates(step) {
    const violations = [];
    
    // Create a copy of current valve states
    const simulatedStates = {};
    State.valves.forEach(v => {
        simulatedStates[v.id] = v.current_state;
    });
    
    // Helper function to check if current simulated state is invalid
    const checkCurrentState = () => {
        if (!CONFIG.invalidValveStates || !Array.isArray(CONFIG.invalidValveStates)) {
            return null;
        }
        
        for (const rule of CONFIG.invalidValveStates) {
            const openValves = rule.open || [];
            const closedValves = rule.closed || [];
            
            const openMatch = openValves.every(id => simulatedStates[id] === 'open');
            const closedMatch = closedValves.every(id => simulatedStates[id] === 'closed');
            
            if (openMatch && closedMatch && (openValves.length > 0 || closedValves.length > 0)) {
                // Build array of "Name (id) state" strings
                const valveDescriptions = [];
                openValves.forEach(id => {
                    const v = State.valves.find(valve => valve.id === id);
                    const name = v ? `${v.name} (${id})` : `Valve ${id}`;
                    valveDescriptions.push(`${name} open`);
                });
                closedValves.forEach(id => {
                    const v = State.valves.find(valve => valve.id === id);
                    const name = v ? `${v.name} (${id})` : `Valve ${id}`;
                    valveDescriptions.push(`${name} closed`);
                });
                
                // Format with commas and "and" before last item
                let desc = 'Invalid state would occur: ';
                if (valveDescriptions.length === 1) {
                    desc += valveDescriptions[0];
                } else if (valveDescriptions.length === 2) {
                    desc += `${valveDescriptions[0]} and ${valveDescriptions[1]}`;
                } else {
                    const lastItem = valveDescriptions.pop();
                    desc += `${valveDescriptions.join(', ')}, and ${lastItem}`;
                }
                desc += '.';
                return desc;
            }
        }
        return null;
    };
    
    // Simulate each action in the step
    const actions = step.actions || [];
    for (const action of actions) {
        // Handle multi-actions (arrays)
        if (Array.isArray(action)) {
            for (const subAction of action) {
                if (subAction.type === 'set_valve') {
                    simulatedStates[subAction.valve_id] = subAction.state;
                } else if (subAction.type === 'pulse_valve') {
                    // Pulse temporarily changes state then returns
                    // Check the pulsed state
                    const originalState = simulatedStates[subAction.valve_id];
                    const pulseState = originalState === 'open' ? 'closed' : 'open';
                    simulatedStates[subAction.valve_id] = pulseState;
                    
                    const pulseViolation = checkCurrentState();
                    if (pulseViolation && !violations.includes(pulseViolation)) {
                        violations.push(pulseViolation);
                    }
                    
                    // Return to original state after pulse
                    simulatedStates[subAction.valve_id] = originalState;
                }
            }
            // Check state after multi-action completes
            const violation = checkCurrentState();
            if (violation && !violations.includes(violation)) {
                violations.push(violation);
            }
        } else {
            // Single action
            if (action.type === 'set_valve') {
                simulatedStates[action.valve_id] = action.state;
                const violation = checkCurrentState();
                if (violation && !violations.includes(violation)) {
                    violations.push(violation);
                }
            } else if (action.type === 'pulse_valve') {
                // Pulse temporarily changes state then returns
                const originalState = simulatedStates[action.valve_id];
                const pulseState = originalState === 'open' ? 'closed' : 'open';
                simulatedStates[action.valve_id] = pulseState;
                
                const pulseViolation = checkCurrentState();
                if (pulseViolation && !violations.includes(pulseViolation)) {
                    violations.push(pulseViolation);
                }
                
                // Return to original state after pulse
                simulatedStates[action.valve_id] = originalState;
            }
            // 'wait' actions don't change valve states
        }
    }
    
    return violations;
}

/**
 * Executes a procedure step with validation
 */
async function executeStep(index, event) {
    if (event) event.stopPropagation();
    
    if (!State.selectedProcedure) return;
    
    // Check if system is being safed
    if (State.safingSystem) {
        const userInfo = State.safingSystemUser ? ` by ${State.safingSystemUser}` : '';
        Modal.show(
            'System Safing',
            `<p>The system is currently being safed${userInfo}. Please wait for it to complete before executing a step.</p>`,
            [{ label: 'OK', type: 'primary' }]
        );
        return;
    }
    
    // Check if a step is already executing
    if (State.executingStepIndex !== null) {
        const executorInfo = State.executingStepUser ? ` by ${State.executingStepUser}` : '';
        Modal.show(
            'Step Already Executing',
            `<p>Step ${State.executingStepIndex + 1} is currently executing${executorInfo}. Please wait for it to complete before executing another step.</p>`,
            [{ label: 'OK', type: 'primary' }]
        );
        return;
    }
    
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
    
    // Check for invalid valve states that would occur during step execution
    const invalidStateViolations = checkStepInvalidStates(step);
    invalidStateViolations.forEach(v => warnings.push(v));
    
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
 * Performs the actual step execution by requesting the server to execute it.
 * The server handles all action execution; the client just polls for status updates.
 */
async function performStepExecution(index, step) {
    logStatus(`Requesting execution of step ${index + 1}: ${step.name}`);
    
    // Request server to execute the step
    try {
        const result = await API.startStepExecution(State.selectedProcedureIndex, index);
        if (result.status === 'error') {
            // Another step is already executing
            if (result.executing) {
                Modal.show(
                    'Step Already Executing',
                    `<p>Step ${result.executing.step_index + 1} is currently being executed by another user (${result.executing.user}). Please wait for it to complete.</p>`,
                    [{ label: 'OK', type: 'primary' }]
                );
            } else {
                Modal.show(
                    'Execution Failed',
                    `<p>${result.message || 'Failed to start step execution'}</p>`,
                    [{ label: 'OK', type: 'primary' }]
                );
            }
            return;
        }
        
        logStatus(`Step ${index + 1} execution started on server`);
        // Server is now executing the step - status polling will update the UI
        
    } catch (error) {
        logError('Failed to start step execution on server', error);
        Modal.show(
            'Execution Failed',
            `<p>Failed to start step execution: ${error.message}</p>`,
            [{ label: 'OK', type: 'primary' }]
        );
    }
}

/**
 * Initial data load
 */
async function initialLoad() {
    try {
        const [valves, sensors, procedures, invalidValveStates, titleData] = await Promise.all([
            API.getValveInfo(),
            API.getSensorInfo(),
            API.getProcedures(),
            API.getInvalidValveStates(),
            API.getWebsiteTitle()
        ]);
        
        State.valves = valves;
        State.sensors = sensors;
        
        // Update CONFIG with fetched data
        CONFIG.procedures = procedures;
        CONFIG.invalidValveStates = invalidValveStates;
        
        // Update website title
        if (titleData && titleData.title) {
            document.title = titleData.title;
            const headerTitle = document.querySelector('.header-left h1');
            if (headerTitle) {
                headerTitle.textContent = titleData.title;
            }
        }
        
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
 * Updates the header time display
 */
function updateHeaderTime() {
    const timeElement = document.getElementById('header-time');
    if (timeElement) {
        const now = new Date();
        const timeString = now.toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit',
            hour12: true 
        });
        timeElement.textContent = timeString;
    }
}

/**
 * Application initialization
 */
async function init() {
    logStatus('Ground Control System initializing...');
    
    // Start time display update
    updateHeaderTime();
    setInterval(updateHeaderTime, 1000);
    
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
    procedurePollingLoop();
    procedureStatusPollingLoop();
    safingStatusPollingLoop();
    
    logStatus('Ground Control System initialized');
}

document.addEventListener('DOMContentLoaded', init);
