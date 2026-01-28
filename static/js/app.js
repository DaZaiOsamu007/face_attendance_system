class AttendanceSystem {
    constructor() {
        this.video = document.getElementById('video');
        this.canvas = document.getElementById('canvas');
        this.ctx = this.canvas.getContext('2d');
        this.stream = null;
        this.isProcessing = false;

        this.initializeEventListeners();
        this.loadDashboardData();
        this.loadHistory();
    }

    initializeEventListeners() {
        document.getElementById('startCamera').addEventListener('click', () => {
            this.startCamera();
        });
        document.getElementById('stopCamera').addEventListener('click', () => {
            this.stopCamera();
        });

        document.getElementById('registerBtn').addEventListener('click', () => {
            this.registerUser();
        });

        document.getElementById('authenticateBtn').addEventListener('click', () => {
            this.authenticateUser();
        });

        document.getElementById('refreshHistory').addEventListener('click', () => {
            this.loadHistory();
        });

        document.getElementById('userName').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.registerUser();
            }
        });
    }

    async startCamera() {
        try {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                alert('Camera access is not supported in your browser. Please use Chrome, Edge, or Firefox.');
                return;
            }

            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    facingMode: 'user'
                }
            });

            this.video.srcObject = this.stream;

            this.video.onloadedmetadata = () => {
                this.video.play().then(() => {
                }).catch(err => {
                    console.error('Error playing video:', err);
                });
            };

            document.getElementById('startCamera').disabled = true;
            document.getElementById('stopCamera').disabled = false;
            document.querySelector('.status-indicator').classList.add('active');

            alert('Camera started! You should see yourself in the video.');

        } catch (error) {
            console.error('Camera error:', error);
            console.error('Error name:', error.name);
            console.error('Error message:', error.message);

            let errorMessage = 'Failed to access camera: ';

            if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
                errorMessage += 'Permission denied. Please allow camera access in your browser settings.';
            } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
                errorMessage += 'No camera found. Please connect a camera and try again.';
            } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
                errorMessage += 'Camera is already in use by another application. Please close other apps and try again.';
            } else {
                errorMessage += error.message;
            }

            alert(errorMessage);
        }
    }

    stopCamera() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => {
                track.stop();
            });
            this.video.srcObject = null;

            document.getElementById('startCamera').disabled = false;
            document.getElementById('stopCamera').disabled = true;
            document.querySelector('.status-indicator').classList.remove('active');

            alert('Camera stopped');
        }
    }

    captureFrame() {
        if (!this.stream) {
            alert('Please start the camera first!');
            return null;
        }

        this.canvas.width = this.video.videoWidth;
        this.canvas.height = this.video.videoHeight;

        this.ctx.drawImage(this.video, 0, 0);

        const imageData = this.canvas.toDataURL('image/jpeg');

        return imageData;
    }

    async registerUser() {
        if (this.isProcessing) {
            return;
        }

        const name = document.getElementById('userName').value.trim();

        if (!name) {
            this.showResult('registerResult', 'Please enter your name!', 'error');
            return;
        }

        const imageData = this.captureFrame();
        if (!imageData) {
            return;
        }

        this.isProcessing = true;
        document.getElementById('registerBtn').disabled = true;
        this.showResult('registerResult', 'Processing registration...', 'warning');

        try {
            const response = await fetch('/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name: name,
                    image: imageData
                })
            });

            const result = await response.json();

            if (result.success) {
                this.showResult('registerResult',
                    `${result.message}<br>Liveness Score: ${result.liveness_score.toFixed(2)}`,
                    'success'
                );
                document.getElementById('userName').value = '';
                this.loadDashboardData();
            } else {
                this.showResult('registerResult', `${result.message}`, 'error');
            }

        } catch (error) {
            console.error('Registration error:', error);
            this.showResult('registerResult', `Error: ${error.message}`, 'error');
        } finally {
            this.isProcessing = false;
            document.getElementById('registerBtn').disabled = false;
        }
    }

    async authenticateUser() {
        if (this.isProcessing) {
            return;
        }

        const imageData = this.captureFrame();
        if (!imageData) {
            return;
        }

        this.isProcessing = true;
        document.getElementById('authenticateBtn').disabled = true;
        this.showResult('authResult', 'Authenticating...', 'warning');

        try {
            const response = await fetch('/authenticate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    image: imageData
                })
            });

            const result = await response.json();

            if (result.success) {
                const punchClass = result.punch_type === 'PUNCH-IN' ? 'punch-in' : 'punch-out';
                this.showResult('authResult',
                    `Welcome, <strong>${result.name}</strong>!<br>
                    <span class="${punchClass}">${result.punch_type}</span> recorded at ${result.timestamp}<br>
                    Confidence: ${(result.confidence * 100).toFixed(1)}% | Liveness: ${result.liveness_score.toFixed(2)}`,
                    'success'
                );
                this.loadDashboardData();
                this.loadHistory();

                this.playSuccessSound();

            } else {
                this.showResult('authResult', `${result.message}`, 'error');
            }

        } catch (error) {
            console.error('Authentication error:', error);
            this.showResult('authResult', `Error: ${error.message}`, 'error');
        } finally {
            this.isProcessing = false;
            document.getElementById('authenticateBtn').disabled = false;
        }
    }

    async loadDashboardData() {
        try {
            const usersResponse = await fetch('/users');
            const usersData = await usersResponse.json();

            if (usersData.success) {
                document.getElementById('userCount').textContent = usersData.users.length;
            }

            const historyResponse = await fetch('/history');
            const historyData = await historyResponse.json();

            if (historyData.success) {
                const today = new Date().toISOString().split('T')[0];
                const todayRecords = historyData.history.filter(record =>
                    record.timestamp.startsWith(today)
                );
                document.getElementById('todayCount').textContent = todayRecords.length;
            }

        } catch (error) {
            console.error('Error loading dashboard data:', error);
        }
    }

    async loadHistory() {
        try {
            const response = await fetch('/history');
            const data = await response.json();

            const tbody = document.getElementById('historyBody');
            tbody.innerHTML = '';

            if (data.success && data.history.length > 0) {
                data.history.forEach(record => {
                    const row = document.createElement('tr');
                    const punchClass = record.punch_type === 'PUNCH-IN' ? 'punch-in' : 'punch-out';

                    row.innerHTML = `
                        <td>${this.escapeHtml(record.name)}</td>
                        <td><span class="${punchClass}">${record.punch_type}</span></td>
                        <td>${record.timestamp}</td>
                        <td>${(parseFloat(record.confidence) * 100).toFixed(1)}%</td>
                    `;

                    tbody.appendChild(row);
                });
            } else {
                tbody.innerHTML = '<tr><td colspan="4" class="no-data">No records found</td></tr>';
            }

        } catch (error) {
            console.error('Error loading history:', error);
            document.getElementById('historyBody').innerHTML =
                '<tr><td colspan="4" class="no-data">Error loading history</td></tr>';
        }
    }

    showResult(elementId, message, type) {
        const resultBox = document.getElementById(elementId);
        resultBox.innerHTML = message;
        resultBox.className = `result-box ${type} show`;

        if (type !== 'warning') {
            setTimeout(() => {
                resultBox.classList.remove('show');
            }, 5000);
        }
    }

    playSuccessSound() {
        try {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();

            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);

            oscillator.frequency.value = 800;
            oscillator.type = 'sine';

            gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);

            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.3);

        } catch (error) {
            console.log('Could not play sound:', error);
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const system = new AttendanceSystem();

    setInterval(() => {
        system.loadHistory();
        system.loadDashboardData();
    }, 30000);
});