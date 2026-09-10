const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');

test('Breeze keeps the shared sample selector after queue.js loads and engine switches', () => {
    const engine = { value: 'breeze_tts_2' };
    const control = () => ({
        hidden: false,
        style: { setProperty(name, value) { this[name] = value; } },
        querySelector: () => null,
    });
    const catalogControl = control();
    const referenceControl = control();
    const catalog = { value: 'af_alloy', innerHTML: '', disabled: false };
    const sample = {
        value: '', dataset: { speaker: 'liam-male' }, options: [],
        set innerHTML(value) { this.options = []; },
        appendChild(option) { this.options.push(option); },
        querySelector(selector) {
            const value = selector.match(/value="([^"]+)"/)?.[1];
            return this.options.find(option => option.value === value) || null;
        },
        closest: () => row,
    };
    const play = { disabled: true };
    const row = {
        dataset: { speaker: 'liam-male' },
        querySelector(selector) {
            return {
                '[data-role="kokoro-control"]': catalogControl,
                '[data-role="turbo-control"]': referenceControl,
                '.reference-select': sample,
                '[data-role="voice-sample-preview-btn"]': play,
            }[selector] || null;
        },
    };
    const context = vm.createContext({
        console, setInterval: () => 0,
        fetch: async () => ({ json: async () => ({ success: false }) }),
        CSS: { escape: value => value },
        document: {
            addEventListener() {},
            getElementById: id => id === 'job-tts-engine' ? engine : null,
            createElement: () => ({ value: '', textContent: '', dataset: {}, style: {} }),
            querySelectorAll(selector) {
                if (selector.includes('.reference-select')) return [sample];
                if (selector.includes('.voice-select')) return [catalog];
                if (selector.includes('.voice-assignment-row')) return [row];
                return [];
            },
        },
    });
    context.window = context;
    context.addEventListener = () => {};
    context.availableVoices = {};
    // Execute the real scripts together, in the order used by index.html.
    // Previously queue.js overwrote main.js's isTurboEngine function here.
    for (const name of ['main.js', 'queue.js']) {
        vm.runInContext(fs.readFileSync(path.join(root, 'static/js', name), 'utf8'), context, { filename: name });
    }
    vm.runInContext(`availableChatterboxVoices = [
        { name: 'liam-male', prompt_path: 'liam_male.wav', transcript: 'The preview words.', duration_seconds: 12.7 },
        { name: 'Other saved voice', prompt_path: 'other.wav', transcript: 'Another preview.', duration_seconds: 14 }
    ];`, context);

    for (const name of ['breeze_tts_2', 'omnivoice_clone', 'breeze_tts_2']) {
        engine.value = name;
        assert.equal(context.isPromptEngine(name), true, name);
        context.populateVoiceSelects();
        assert.equal(context.syncSpeakerReferenceAssignment('liam-male', 'liam_male.wav'), true);
        assert.equal(catalogControl.hidden, true);
        assert.equal(referenceControl.hidden, false);
        assert.equal(catalog.disabled, true);
        assert.equal(sample.value, 'liam_male.wav');
        assert.equal(play.disabled, false);
        assert.deepEqual(sample.options.filter(option => option.value).map(option => option.value),
            ['liam_male.wav', 'other.wav']);
    }
});
