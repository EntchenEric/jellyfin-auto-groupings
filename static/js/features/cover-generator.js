// cover-generator.js – Canvas-based cover image generation

import { state } from '../core/state.js';
import { saveConfig, uploadCover } from '../core/api.js';
import { showToast, getEl } from '../core/ui.js';

let activeCoverIndex = -1;

function mulberry32(a) {
    return function () {
        let t = a += 0x6D2B79F5;
        t = Math.imul(t ^ t >>> 15, t | 1);
        t ^= t + Math.imul(t ^ t >>> 7, t | 61);
        return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
}

function getSeed(str) {
    let hash = 2166136261;
    for (let i = 0; i < str.length; i++) {
        hash ^= str.charCodeAt(i);
        hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
}

function roundRect(ctx, x, y, width, height, radius) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + width - radius, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    ctx.lineTo(x + width, y + height - radius);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    ctx.lineTo(x + radius, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
}

function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
    const words = text.split(' ');
    let line = '';
    const lines = [];
    for (let n = 0; n < words.length; n++) {
        const word = words[n];
        const testLine = line + word + ' ';
        let metrics = ctx.measureText(testLine);
        if (metrics.width > maxWidth) {
            if (line !== '') {
                lines.push(line);
                line = '';
                metrics = ctx.measureText(word + ' ');
            }
            if (metrics.width > maxWidth) {
                const chars = word.split('');
                let segment = '';
                for (let c = 0; c < chars.length; c++) {
                    const testSegment = segment + chars[c];
                    if (ctx.measureText(testSegment).width > maxWidth && segment !== '') {
                        lines.push(segment);
                        segment = chars[c];
                    } else {
                        segment = testSegment;
                    }
                }
                line = segment + ' ';
            } else {
                line = word + ' ';
            }
        } else {
            line = testLine;
        }
    }
    lines.push(line);

    const startY = y - ((lines.length - 1) * lineHeight) / 2;
    for (let i = 0; i < lines.length; i++) {
        ctx.fillText(lines[i].trim(), x, startY + (i * lineHeight));
    }
}

const themeFunctions = {
    'modern-dark': (ctx, w, h, { color1, color2 }, hlp) => {
        const grad = ctx.createLinearGradient(0, 0, w, h);
        grad.addColorStop(0, '#1a1a24');
        grad.addColorStop(1, '#0b0b10');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, w, h);

        const rgb1 = hlp.hexToRgb(color1);
        const rgb2 = hlp.hexToRgb(color2);

        const blob1 = ctx.createRadialGradient(w / 4, h / 2, 0, w / 4, h / 2, 800);
        blob1.addColorStop(0, `rgba(${rgb1.r}, ${rgb1.g}, ${rgb1.b}, 0.2)`);
        blob1.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = blob1;
        ctx.fillRect(0, 0, w, h);

        const blob2 = ctx.createRadialGradient(w * 0.75, h / 2, 0, w * 0.75, h / 2, 800);
        blob2.addColorStop(0, `rgba(${rgb2.r}, ${rgb2.g}, ${rgb2.b}, 0.2)`);
        blob2.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = blob2;
        ctx.fillRect(0, 0, w, h);
    },
    'vibrant-glow': (ctx, w, h, { color1, color2 }, hlp) => {
        const grad = ctx.createLinearGradient(0, 0, w, h);
        grad.addColorStop(0, color1);
        grad.addColorStop(1, color2);
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, w, h);

        const rgb1 = hlp.hexToRgb(color1);
        const rgb2 = hlp.hexToRgb(color2);

        ctx.globalAlpha = 0.6;
        const glow1 = ctx.createRadialGradient(w * 0.3, h * 0.3, 0, w * 0.3, h * 0.3, w * 0.8);
        glow1.addColorStop(0, `rgba(${rgb1.r}, ${rgb1.g}, ${rgb1.b}, 1)`);
        glow1.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = glow1;
        ctx.fillRect(0, 0, w, h);

        const glow2 = ctx.createRadialGradient(w * 0.7, h * 0.7, 0, w * 0.7, h * 0.7, w * 0.8);
        glow2.addColorStop(0, `rgba(${rgb2.r}, ${rgb2.g}, ${rgb2.b}, 1)`);
        glow2.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = glow2;
        ctx.fillRect(0, 0, w, h);

        ctx.globalAlpha = 0.04;
        for (let i = 0; i < 4000; i++) {
            ctx.fillStyle = i % 2 === 0 ? '#ffffff' : '#000000';
            ctx.fillRect(hlp.seededRand() * w, hlp.seededRand() * h, 2, 2);
        }
        ctx.globalAlpha = 1.0;
    },
    'minimal-glass': (ctx, w, h, { color1, color2 }) => {
        ctx.fillStyle = '#f8fafc';
        ctx.fillRect(0, 0, w, h);

        ctx.fillStyle = color1;
        ctx.beginPath(); ctx.arc(w - 200, 250, 400, 0, Math.PI * 2); ctx.fill();

        ctx.fillStyle = color2;
        ctx.beginPath(); ctx.arc(300, h - 300, 500, 0, Math.PI * 2); ctx.fill();

        ctx.fillStyle = 'rgba(255,255,255,0.7)';
        ctx.fillRect(100, 100, w - 200, h - 200);
        ctx.strokeStyle = 'rgba(255,255,255,0.9)';
        ctx.lineWidth = 4;
        ctx.strokeRect(100, 100, w - 200, h - 200);
    },
    'cyberpunk': (ctx, w, h, { color1, color2 }, hlp) => {
        ctx.fillStyle = '#050505';
        ctx.fillRect(0, 0, w, h);

        const rgb1 = hlp.hexToRgb(color1);
        const rgb2 = hlp.hexToRgb(color2);

        const g1 = ctx.createRadialGradient(w * 0.2, h * 0.3, 0, w * 0.2, h * 0.3, 600);
        g1.addColorStop(0, `rgba(${rgb1.r}, ${rgb1.g}, ${rgb1.b}, 0.3)`);
        g1.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = g1;
        ctx.fillRect(0, 0, w, h);

        const g2 = ctx.createRadialGradient(w * 0.8, h * 0.7, 0, w * 0.8, h * 0.7, 800);
        g2.addColorStop(0, `rgba(${rgb2.r}, ${rgb2.g}, ${rgb2.b}, 0.25)`);
        g2.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = g2;
        ctx.fillRect(0, 0, w, h);

        ctx.strokeStyle = 'rgba(255,255,255,0.03)';
        ctx.lineWidth = 1;
        for (let i = 0; i < h; i += 4) {
            ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(w, i); ctx.stroke();
        }

        ctx.fillStyle = color1;
        ctx.globalAlpha = 0.2;
        for (let i = 0; i < 5; i++) {
            ctx.fillRect(hlp.seededRand() * w, hlp.seededRand() * h, hlp.seededRand() * 200, 2);
        }
        ctx.fillStyle = color2;
        for (let i = 0; i < 5; i++) {
            ctx.fillRect(hlp.seededRand() * w, hlp.seededRand() * h, hlp.seededRand() * 150, 1);
        }
        ctx.globalAlpha = 1.0;
    },
    'aurora': (ctx, w, h, { color1, color2 }) => {
        ctx.fillStyle = '#0a0a1a';
        ctx.fillRect(0, 0, w, h);

        ctx.filter = 'blur(120px)';
        ctx.globalAlpha = 0.4;

        ctx.fillStyle = color1;
        ctx.beginPath();
        ctx.moveTo(-100, h * 0.5);
        ctx.bezierCurveTo(w * 0.25, h * 0.2, w * 0.75, h * 0.8, w + 100, h * 0.4);
        ctx.lineTo(w + 100, h * 0.6);
        ctx.bezierCurveTo(w * 0.75, h * 0.9, w * 0.25, h * 0.3, -100, h * 0.7);
        ctx.fill();

        ctx.fillStyle = color2;
        ctx.beginPath();
        ctx.moveTo(-100, h * 0.2);
        ctx.bezierCurveTo(w * 0.3, h * 0.5, w * 0.7, h * 0.1, w + 100, h * 0.3);
        ctx.lineTo(w + 100, h * 0.4);
        ctx.bezierCurveTo(w * 0.7, h * 0.2, w * 0.3, h * 0.6, -100, h * 0.3);
        ctx.fill();

        ctx.filter = 'none';
        ctx.globalAlpha = 1.0;
    },
    'monochrome': (ctx, w, h, { color1, color2 }, hlp) => {
        ctx.fillStyle = '#111827';
        ctx.fillRect(0, 0, w, h);

        ctx.fillStyle = color1;
        ctx.globalAlpha = 0.1;
        for (let i = 0; i < 8; i++) {
            ctx.beginPath();
            ctx.moveTo(hlp.seededRand() * w, hlp.seededRand() * h);
            ctx.lineTo(hlp.seededRand() * w, hlp.seededRand() * h);
            ctx.lineTo(hlp.seededRand() * w, hlp.seededRand() * h);
            ctx.fill();
        }

        ctx.fillStyle = color2;
        ctx.globalAlpha = 0.05;
        for (let i = 0; i < 12; i++) {
            ctx.beginPath();
            ctx.moveTo(hlp.seededRand() * w, hlp.seededRand() * h);
            ctx.lineTo(hlp.seededRand() * w, hlp.seededRand() * h);
            ctx.lineTo(hlp.seededRand() * w, hlp.seededRand() * h);
            ctx.fill();
        }
        ctx.globalAlpha = 1.0;
    },
    'vintage': (ctx, w, h, { color1 }, hlp) => {
        ctx.fillStyle = '#fdf4ff';
        ctx.fillRect(0, 0, w, h);

        ctx.fillStyle = color1;
        ctx.globalAlpha = 0.15;
        ctx.fillRect(0, 0, w, h);

        const vig = ctx.createRadialGradient(w / 2, h / 2, w / 4, w / 2, h / 2, w);
        vig.addColorStop(0, 'rgba(0,0,0,0)');
        vig.addColorStop(1, 'rgba(0,0,0,0.6)');
        ctx.fillStyle = vig;
        ctx.globalAlpha = 1.0;
        ctx.fillRect(0, 0, w, h);

        ctx.fillStyle = '#000000';
        ctx.globalAlpha = 0.05;
        for (let i = 0; i < 2000; i++) {
            ctx.fillRect(hlp.seededRand() * w, hlp.seededRand() * h, 1, 1);
        }
        ctx.globalAlpha = 1.0;
    }
};

export function openCoverGenerator(index) {
    activeCoverIndex = index;
    const group = state.currentConfig.groups[index];

    getEl('cover-text').value = group.cover_text || group.name || 'Custom Group';
    getEl('cover-theme').value = group.cover_theme || 'modern-dark';
    getEl('cover-border-style').value = group.cover_border_style || 'none';
    getEl('cover-border-color').value = group.cover_border_color || '#ffffff';
    getEl('cover-color-1').value = group.cover_color1 || '#4f46e5';
    getEl('cover-color-2').value = group.cover_color2 || '#9333ea';

    getEl('cover-generator-modal').style.display = 'flex';

    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(() => renderCover());
    } else {
        setTimeout(() => renderCover(), 100);
    }
}

export function renderCover() {
    const canvas = getEl('cover-canvas');
    const ctx = canvas.getContext('2d');
    const text = getEl('cover-text').value.trim() || 'Group Name';
    const theme = getEl('cover-theme').value;
    const color1 = getEl('cover-color-1').value;
    const color2 = getEl('cover-color-2').value;

    const seed = getSeed(text + theme + color1 + color2);
    const seededRand = mulberry32(seed);

    const dpr = window.devicePixelRatio || 1;
    const logicalW = 1920;
    const logicalH = 1080;

    if (canvas.width !== logicalW * dpr) {
        canvas.width = logicalW * dpr;
        canvas.height = logicalH * dpr;
        canvas.style.width = logicalW + 'px';
        canvas.style.height = logicalH + 'px';
    }

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const w = logicalW;
    const h = logicalH;

    ctx.clearRect(0, 0, w, h);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';

    const helpers = {
        hexToRgb: (hex) => {
            const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
            return result ? {
                r: parseInt(result[1], 16),
                g: parseInt(result[2], 16),
                b: parseInt(result[3], 16)
            } : { r: 0, g: 0, b: 0 };
        },
        roundRect,
        wrapText,
        seededRand
    };

    if (themeFunctions[theme]) {
        themeFunctions[theme](ctx, w, h, { color1, color2 }, helpers);
    }

    ctx.filter = 'none';
    ctx.globalAlpha = 1.0;
    ctx.shadowBlur = 0;
    ctx.shadowColor = 'transparent';

    // Border drawing
    const borderStyle = getEl('cover-border-style').value;
    const borderColor = getEl('cover-border-color').value;

    if (borderStyle !== 'none') {
        if (borderStyle === 'elegant') {
            const m = 40;
            ctx.strokeStyle = borderColor;
            ctx.lineWidth = 12; ctx.globalAlpha = 0.15;
            roundRect(ctx, m, m, w - m * 2, h - m * 2, 20); ctx.stroke();
            ctx.lineWidth = 2; ctx.globalAlpha = 0.9;
            roundRect(ctx, m + 4, m + 4, w - (m + 4) * 2, h - (m + 4) * 2, 16); ctx.stroke();
            ctx.globalAlpha = 1.0;
        } else if (borderStyle === 'bold-frame') {
            const m = 45;
            ctx.shadowColor = 'rgba(0,0,0,0.6)'; ctx.shadowBlur = 30; ctx.shadowOffsetY = 15;
            ctx.strokeStyle = borderColor; ctx.lineWidth = 30;
            roundRect(ctx, m, m, w - m * 2, h - m * 2, 35); ctx.stroke();
            ctx.shadowColor = 'transparent';
            ctx.strokeStyle = 'rgba(255,255,255,0.4)'; ctx.lineWidth = 4;
            const im = m + 13; roundRect(ctx, im, im, w - im * 2, h - im * 2, 22); ctx.stroke();
            ctx.strokeStyle = 'rgba(0,0,0,0.4)'; ctx.lineWidth = 4;
            const om = m - 13; roundRect(ctx, om, om, w - om * 2, h - om * 2, 48); ctx.stroke();
        } else if (borderStyle === 'neon-glow') {
            const m = 55;
            ctx.shadowColor = borderColor; ctx.shadowBlur = 80;
            ctx.strokeStyle = borderColor; ctx.lineWidth = 15; ctx.globalAlpha = 0.4;
            roundRect(ctx, m, m, w - m * 2, h - m * 2, 30); ctx.stroke();
            ctx.shadowBlur = 20; ctx.lineWidth = 8; ctx.globalAlpha = 0.8;
            roundRect(ctx, m, m, w - m * 2, h - m * 2, 30); ctx.stroke();
            ctx.shadowColor = 'transparent'; ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 4; ctx.globalAlpha = 1.0;
            roundRect(ctx, m, m, w - m * 2, h - m * 2, 30); ctx.stroke();
        } else if (borderStyle === 'tech-corners') {
            const m = 50; const len = 140; const chamfer = 25;
            ctx.strokeStyle = borderColor; ctx.lineWidth = 8; ctx.lineJoin = 'miter';
            ctx.beginPath();
            ctx.moveTo(m, m + len); ctx.lineTo(m, m + chamfer); ctx.lineTo(m + chamfer, m); ctx.lineTo(m + len, m);
            ctx.moveTo(w - m - len, m); ctx.lineTo(w - m - chamfer, m); ctx.lineTo(w - m, m + chamfer); ctx.lineTo(w - m, m + len);
            ctx.moveTo(w - m, h - m - len); ctx.lineTo(w - m, h - m - chamfer); ctx.lineTo(w - m - chamfer, h - m); ctx.lineTo(w - m - len, h - m);
            ctx.moveTo(m + len, h - m); ctx.lineTo(m + chamfer, h - m); ctx.lineTo(m, h - m - chamfer); ctx.lineTo(m, h - m - len);
            ctx.stroke();
            ctx.lineWidth = 2; ctx.globalAlpha = 0.5; const im2 = m + 18;
            ctx.beginPath();
            ctx.moveTo(im2, im2 + len - 20); ctx.lineTo(im2, im2); ctx.lineTo(im2 + len - 20, im2);
            ctx.moveTo(w - im2 - len + 20, im2); ctx.lineTo(w - im2, im2); ctx.lineTo(w - im2, im2 + len - 20);
            ctx.moveTo(w - im2, h - im2 - len + 20); ctx.lineTo(w - im2, h - im2); ctx.lineTo(w - im2 - len + 20, h - im2);
            ctx.moveTo(im2 + len - 20, h - im2); ctx.lineTo(im2, h - im2); ctx.lineTo(im2, h - im2 - len + 20);
            ctx.stroke(); ctx.globalAlpha = 1.0;
            ctx.fillStyle = borderColor; const blockOffset = m + len + 15;
            ctx.fillRect(blockOffset, m - 4, 30, 8); ctx.fillRect(blockOffset + 40, m - 4, 10, 8);
            ctx.fillRect(w - blockOffset - 30, m - 4, 30, 8);
            ctx.fillRect(blockOffset, h - m - 4, 40, 8); ctx.fillRect(w - blockOffset - 20, h - m - 4, 20, 8);
            ctx.fillRect(w - blockOffset - 40, h - m - 4, 10, 8);
        } else if (borderStyle === 'double-inset') {
            const m1 = 40; const m2 = 55; ctx.strokeStyle = borderColor; ctx.lineWidth = 2;
            roundRect(ctx, m1, m1, w - m1 * 2, h - m1 * 2, 20); ctx.stroke();
            roundRect(ctx, m2, m2, w - m2 * 2, h - m2 * 2, 10); ctx.stroke();
        } else if (borderStyle === 'corner-brackets') {
            const m = 40; const len = 100; ctx.strokeStyle = borderColor; ctx.lineWidth = 12; ctx.lineCap = 'square';
            ctx.beginPath(); ctx.moveTo(m, m + len); ctx.lineTo(m, m); ctx.lineTo(m + len, m); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(w - m - len, m); ctx.lineTo(w - m, m); ctx.lineTo(w - m, m + len); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(w - m, h - m - len); ctx.lineTo(w - m, h - m); ctx.lineTo(w - m - len, h - m); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(m + len, h - m); ctx.lineTo(m, h - m); ctx.lineTo(m, h - m - len); ctx.stroke();
        } else if (borderStyle === 'industrial-dash') {
            const m = 50; ctx.strokeStyle = borderColor; ctx.lineWidth = 8; ctx.setLineDash([40, 20]);
            roundRect(ctx, m, m, w - m * 2, h - m * 2, 20); ctx.stroke(); ctx.setLineDash([]);
        } else if (borderStyle === 'ornate') {
            const m = 60; ctx.strokeStyle = borderColor; ctx.lineWidth = 4;
            roundRect(ctx, m, m, w - m * 2, h - m * 2, 30); ctx.stroke();
            const r = 15; ctx.fillStyle = borderColor;
            ctx.beginPath(); ctx.arc(w / 2, m, r, 0, Math.PI * 2); ctx.fill();
            ctx.beginPath(); ctx.arc(w / 2, h - m, r, 0, Math.PI * 2); ctx.fill();
            ctx.beginPath(); ctx.arc(m, h / 2, r, 0, Math.PI * 2); ctx.fill();
            ctx.beginPath(); ctx.arc(w - m, h / 2, r, 0, Math.PI * 2); ctx.fill();
        }
    }

    ctx.shadowBlur = 0;
    ctx.shadowColor = 'transparent';
    ctx.globalAlpha = 1.0;
    ctx.filter = 'none';

    // Text drawing
    if (theme === 'modern-dark') {
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 120px "Outfit", sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        wrapText(ctx, text, w / 2, h / 2 + 50, w - 200, 140);
    } else if (theme === 'vibrant-glow') {
        ctx.fillStyle = '#ffffff';
        ctx.font = '800 140px "Outfit", sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.shadowColor = 'rgba(0,0,0,0.5)'; ctx.shadowBlur = 30;
        wrapText(ctx, text, w / 2, h / 2, w - 200, 160);
    } else if (theme === 'minimal-glass') {
        ctx.fillStyle = '#0f172a';
        ctx.font = '600 130px "Outfit", sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        wrapText(ctx, text, w / 2, h / 2, w - 300, 150);
    } else if (theme === 'cyberpunk') {
        ctx.fillStyle = '#ffffff';
        ctx.font = '900 150px "Outfit", sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.shadowColor = color1; ctx.shadowBlur = 20;
        wrapText(ctx, text, w / 2, h / 2, w - 200, 170);
    } else if (theme === 'aurora') {
        ctx.fillStyle = '#ffffff';
        ctx.font = '300 140px "Outfit", sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.filter = 'blur(1px)';
        wrapText(ctx, text, w / 2, h / 2, w - 300, 160);
    } else if (theme === 'monochrome') {
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 160px "Outfit", sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        wrapText(ctx, text, w / 2, h / 2, w - 200, 180);
    } else if (theme === 'vintage') {
        ctx.fillStyle = '#422006';
        ctx.font = 'italic 500 120px "Outfit", sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.globalAlpha = 0.8;
        wrapText(ctx, text, w / 2, h / 2, w - 300, 140);
    }

    ctx.shadowBlur = 0;
    ctx.shadowColor = 'transparent';
    ctx.globalAlpha = 1.0;
    ctx.filter = 'none';
}

export function downloadCover() {
    if (activeCoverIndex < 0) return;
    const group = state.currentConfig.groups[activeCoverIndex];
    const canvas = getEl('cover-canvas');
    const dataUrl = canvas.toDataURL('image/jpeg', 0.92);

    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = (group.name || 'group_cover') + '_cover.jpg';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToast('Downloaded cover!', 'success');
}

export async function applyCover() {
    if (activeCoverIndex < 0) return;
    const group = state.currentConfig.groups[activeCoverIndex];

    const canvas = getEl('cover-canvas');
    const dataUrl = canvas.toDataURL('image/jpeg', 0.92);

    try {
        await uploadCover(group.name, dataUrl);
        showToast('Cover generated and saved!', 'success');

        group.cover_text = getEl('cover-text').value;
        group.cover_theme = getEl('cover-theme').value;
        group.cover_border_style = getEl('cover-border-style').value;
        group.cover_border_color = getEl('cover-border-color').value;
        group.cover_color1 = getEl('cover-color-1').value;
        group.cover_color2 = getEl('cover-color-2').value;

        await saveConfig(state.currentConfig);
        getEl('cover-generator-modal').style.display = 'none';
        document.dispatchEvent(new CustomEvent('groups-changed'));
    } catch (err) {
        showToast('Network error while saving cover.', 'error');
    }
}

export function initCoverGenerator() {
    // Cover buttons wired via HTML onclicks; renderCover() triggered by openCoverGenerator()
}
