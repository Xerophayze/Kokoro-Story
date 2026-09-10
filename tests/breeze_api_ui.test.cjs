const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

function environment() {
    const elements = new Map();
    const engine = {value: 'breeze_api'};
    elements.set('job-tts-engine', engine);
    const rows = ['alice', 'bob'].map((speaker, index) => {
        const select = {
            value: ['voc_alice', 'voc_bob'][index], options: [], dataset: {speaker},
            set innerHTML(value) { this.options = []; this.value = ''; },
            add(option) { this.options.push(option); },
            appendChild(option) { this.options.push(option); },
            closest() { return row; }
        };
        const row = {dataset: {speaker}, querySelector: s => s === '.voice-select' ? select : null};
        return row;
    });
    const context = vm.createContext({console, setInterval() {},
        fetch: async () => ({json: async () => ({success: false})}),
        Option: function(text, value) {this.text = text; this.value = value;},
        document: {
            addEventListener() {}, getElementById: id => elements.get(id) || null,
            querySelectorAll: s => s.includes('.voice-assignment-row') ? rows : s.includes('.voice-select') ? rows.map(r => r.querySelector('.voice-select')) : [],
            createElement: () => ({appendChild() {}, dataset: {}, style: {}})
        }
    });
    context.window = context;
    context.addEventListener = () => {};
    for (const script of ['main.js', 'breeze-api.js', 'queue.js']) {
        vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js', script), 'utf8'), context);
    }
    return {context, rows, elements};
}

test('Breeze hosted assignments stay separate by speaker, including missing catalog entries', () => {
    const {context, rows} = environment();
    assert.equal(context.isCatalogCloudEngine('breeze_api'), true);
    assert.equal(context.isPromptEngine('breeze_api'), true);
    context.breezeApiVoices = [];
    context.populateVoiceSelects();
    assert.equal(rows[0].querySelector('.voice-select').value, 'voc_alice');
    assert.equal(rows[1].querySelector('.voice-select').value, 'voc_bob');
    const assignments = context.getVoiceAssignments();
    assert.equal(assignments.alice.voice, 'voc_alice');
    assert.equal(assignments.bob.voice, 'voc_bob');
    assert(!JSON.stringify(assignments).includes('af_alloy'));
    rows[0].querySelector('.voice-select').value = 'af_alloy';
    context.populateVoiceSelects();
    assert.equal(rows[0].querySelector('.voice-select').value, '');
    assert(!rows[0].querySelector('.voice-select').options.some(o => o.value === 'af_alloy'));
});

test('Breeze settings round-trip all hosted properties including zero retries', () => {
    const {context, elements} = environment();
    const values = {key: 'test-key', model: 'breeze-tts-2', default_voice: 'voc_alice',
        instructions: 'Speak clearly.', timeout: 180, max_parallel: 2, max_retries: 0,
        guidance_scale: 4, chunk_size: 900};
    const settings = {};
    for (const [key, value] of Object.entries(values)) {
        elements.set(`breeze-api-${key.replaceAll('_', '-')}`, {value: ''});
        settings[`breeze_api_${key}`] = value;
    }
    context.loadBreezeApiSettings(settings);
    assert.deepEqual(JSON.parse(JSON.stringify(context.collectBreezeApiSettings())), settings);
});

test('Breeze submits selected local samples before catalog voices and retains their transcripts', () => {
    const {context, rows} = environment();
    vm.runInContext(`availableChatterboxVoices = [{prompt_path: 'alice.wav', transcript: 'The complete sample.', language: 'English'}];`, context);
    context.availableReferencePrompts = [{name: 'alice.wav', transcript: 'The complete sample.', language: 'English'}];
    const original = rows[0].querySelector;
    const reference = {value: 'alice.wav'};
    rows[0].querySelector = selector => selector === '.reference-select' ? reference : original(selector);
    const assignment = context.getVoiceAssignments().alice;
    assert.equal(assignment.audio_prompt_path, 'alice.wav');
    assert.equal(assignment.extra.prompt_text, 'The complete sample.');
    assert.equal(assignment.extra.breeze_language, 'en');
    assert(!assignment.voice);
    reference.value = '';
    assert.equal(context.getVoiceAssignments().alice.voice, 'voc_alice');
});
