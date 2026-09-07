// orb.js

// 1. WebSocket Connection Setup
const statusEl = document.getElementById('status');
const titleEl = document.getElementById('title');

let currentState = "OFFLINE";
let targetPulseIntensity = 0.0;
let currentPulseIntensity = 0.0;

function connectWebSocket() {
    const ws = new WebSocket('ws://localhost:8765');
    
    ws.onopen = () => {
        statusEl.innerText = "ONLINE";
        statusEl.className = "listening";
        titleEl.className = "listening";
        currentState = "LISTENING";
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.state && data.state !== currentState) {
            currentState = data.state;
            statusEl.innerText = currentState;
            
            // Map state to colors/intensity
            if (currentState === "LISTENING") {
                statusEl.className = "listening";
                titleEl.className = "listening";
                targetPulseIntensity = 0.2;
            } else if (currentState === "RECORDING") {
                statusEl.className = "recording";
                titleEl.className = "recording";
                targetPulseIntensity = 1.0;
            } else if (currentState === "THINKING") {
                statusEl.className = "thinking";
                titleEl.className = "thinking";
                targetPulseIntensity = 0.5;
            } else if (currentState === "SPEAKING") {
                statusEl.className = "speaking";
                titleEl.className = "speaking";
                targetPulseIntensity = 1.5;
            }
        }
    };
    
    ws.onclose = () => {
        statusEl.innerText = "OFFLINE";
        statusEl.className = "";
        titleEl.className = "";
        currentState = "OFFLINE";
        targetPulseIntensity = 0.0;
        setTimeout(connectWebSocket, 2000);
    };
}
connectWebSocket();

// 2. Three.js Setup
const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.z = 5;

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(window.devicePixelRatio);
container.appendChild(renderer.domElement);

// Organic morphing logic
const geometry = new THREE.IcosahedronGeometry(1.2, 32);

// Custom shader material for the glowing orb
const vertexShader = `
    uniform float uTime;
    uniform float uIntensity;
    
    varying vec2 vUv;
    varying vec3 vNormal;
    
    // Simplex 3D Noise function (psuedo-random)
    vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x, 289.0);}
    vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}
    
    float snoise(vec3 v){ 
        const vec2  C = vec2(1.0/6.0, 1.0/3.0) ;
        const vec4  D = vec4(0.0, 0.5, 1.0, 2.0);
        vec3 i  = floor(v + dot(v, C.yyy) );
        vec3 x0 = v - i + dot(i, C.xxx) ;
        vec3 g = step(x0.yzx, x0.xyz);
        vec3 l = 1.0 - g;
        vec3 i1 = min( g.xyz, l.zxy );
        vec3 i2 = max( g.xyz, l.zxy );
        vec3 x1 = x0 - i1 + 1.0 * C.xxx;
        vec3 x2 = x0 - i2 + 2.0 * C.xxx;
        vec3 x3 = x0 - 1.0 + 3.0 * C.xxx;
        i = mod(i, 289.0 ); 
        vec4 p = permute( permute( permute( 
                  i.z + vec4(0.0, i1.z, i2.z, 1.0 ))
                + i.y + vec4(0.0, i1.y, i2.y, 1.0 )) 
                + i.x + vec4(0.0, i1.x, i2.x, 1.0 ));
        float n_ = 1.0/7.0;
        vec3  ns = n_ * D.wyz - D.xzx;
        vec4 j = p - 49.0 * floor(p * ns.z *ns.z);
        vec4 x_ = floor(j * ns.z);
        vec4 y_ = floor(j - 7.0 * x_ );
        vec4 x = x_ *ns.x + ns.yyyy;
        vec4 y = y_ *ns.x + ns.yyyy;
        vec4 h = 1.0 - abs(x) - abs(y);
        vec4 b0 = vec4( x.xy, y.xy );
        vec4 b1 = vec4( x.zw, y.zw );
        vec4 s0 = floor(b0)*2.0 + 1.0;
        vec4 s1 = floor(b1)*2.0 + 1.0;
        vec4 sh = -step(h, vec4(0.0));
        vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy ;
        vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww ;
        vec3 p0 = vec3(a0.xy,h.x);
        vec3 p1 = vec3(a0.zw,h.y);
        vec3 p2 = vec3(a1.xy,h.z);
        vec3 p3 = vec3(a1.zw,h.w);
        vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2, p2), dot(p3,p3)));
        p0 *= norm.x;
        p1 *= norm.y;
        p2 *= norm.z;
        p3 *= norm.w;
        vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
        m = m * m;
        return 42.0 * dot( m*m, vec4( dot(p0,x0), dot(p1,x1), 
                                    dot(p2,x2), dot(p3,x3) ) );
    }
    
    void main() {
        vUv = uv;
        vNormal = normal;
        
        // Morph the vertices based on noise and intensity
        float noise = snoise(vec3(position.x * 2.0 + uTime, position.y * 2.0 + uTime, position.z * 2.0));
        
        // Base displacement + dynamic displacement based on audio/state intensity
        float displacement = (0.05 + 0.15 * uIntensity) * noise;
        vec3 newPosition = position + normal * displacement;
        
        gl_Position = projectionMatrix * modelViewMatrix * vec4(newPosition, 1.0);
    }
`;

const fragmentShader = `
    uniform float uTime;
    uniform vec3 uColor1;
    uniform vec3 uColor2;
    
    varying vec2 vUv;
    varying vec3 vNormal;
    
    void main() {
        // Simple directional lighting for depth
        vec3 light = normalize(vec3(1.0, 1.0, 1.0));
        float dProd = dot(vNormal, light);
        
        // Mix two colors based on UV and time
        vec3 baseColor = mix(uColor1, uColor2, vUv.y + sin(uTime) * 0.2);
        vec3 finalColor = baseColor * (dProd * 0.5 + 0.5);
        
        // Add some emissive glow at the edges
        float intensity = pow(0.7 - dot(vNormal, vec3(0, 0, 1.0)), 2.0);
        finalColor += uColor2 * intensity * 1.5;
        
        gl_FragColor = vec4(finalColor, 1.0);
    }
`;

const material = new THREE.ShaderMaterial({
    vertexShader: vertexShader,
    fragmentShader: fragmentShader,
    uniforms: {
        uTime: { value: 0 },
        uIntensity: { value: 0 },
        // Colors corresponding to the state
        uColor1: { value: new THREE.Color(0x00ffff) }, // Cyan
        uColor2: { value: new THREE.Color(0x0055ff) }  // Deep Blue
    },
    wireframe: false,
    transparent: true,
});

const orb = new THREE.Mesh(geometry, material);
scene.add(orb);

// Animation Loop
const clock = new THREE.Clock();

function animate() {
    requestAnimationFrame(animate);
    
    const time = clock.getElapsedTime();
    orb.rotation.y = time * 0.2;
    orb.rotation.x = time * 0.1;
    
    // Smoothly interpolate the pulse intensity
    currentPulseIntensity += (targetPulseIntensity - currentPulseIntensity) * 0.1;
    
    // Add a heartbeat pulsing effect if we are recording or speaking
    let heartbeat = 0;
    if (currentState === "RECORDING" || currentState === "SPEAKING") {
        // Fast heartbeat pulse
        heartbeat = Math.sin(time * 15.0) * 0.5 + 0.5;
    } else if (currentState === "THINKING") {
        // Slow thinking pulse
        heartbeat = Math.sin(time * 2.0) * 0.2;
    }
    
    material.uniforms.uTime.value = time;
    material.uniforms.uIntensity.value = currentPulseIntensity + heartbeat;
    
    // Smoothly transition colors based on state
    let targetC1 = new THREE.Color(0x00ffff); // Default Listening (Cyan)
    let targetC2 = new THREE.Color(0x0055ff); 
    
    if (currentState === "RECORDING") {
        targetC1 = new THREE.Color(0xff3366); // Red/Pink
        targetC2 = new THREE.Color(0xaa0033);
    } else if (currentState === "THINKING") {
        targetC1 = new THREE.Color(0xbb88ff); // Purple
        targetC2 = new THREE.Color(0x5500aa);
    } else if (currentState === "SPEAKING") {
        targetC1 = new THREE.Color(0x00ffaa); // Green/Cyan
        targetC2 = new THREE.Color(0x008855);
    }
    
    material.uniforms.uColor1.value.lerp(targetC1, 0.05);
    material.uniforms.uColor2.value.lerp(targetC2, 0.05);
    
    renderer.render(scene, camera);
}

animate();

// Handle Resize
window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});
