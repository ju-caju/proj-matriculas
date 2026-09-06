const assert = require('node:assert/strict');
const { createPlanStore } = require('./plan-store.js');

const row = (periodo = '2026.2', turma = '01') => ({
  disciplina: 'CÁLCULO',
  periodo,
  turma,
  horario: '24M23',
  docente: 'DOCENTE',
});

const storage = {
  values: new Map(),
  getItem(key) {
    return this.values.get(key) ?? null;
  },
  setItem(key, value) {
    this.values.set(key, value);
  },
};

const store = createPlanStore({ storage, key: value => JSON.stringify([value.periodo, value.turma]) });
store.save('2026.2', [row(), row('2026.2', '01'), row('2026.2', '02'), row('2027.1')]);
assert.deepEqual(store.load('2026.2').map(value => value.turma), ['01', '02']);
assert.deepEqual(store.load('2027.1'), []);

store.save('2026.2', [row('2025.1', 'fora'), row('2026.2', 'ok')]);
assert.deepEqual(store.load('2026.2').map(value => value.turma), ['ok']);

storage.values.set('ufpb-plan:2026.2', '{invalido');
assert.deepEqual(store.load('2026.2'), []);

console.log('Armazenamento por semestre: OK');

// Old course arrays coexist with commitments and retain semester isolation.
const mixed = createPlanStore({ storage });
const commitment = { type: 'commitment', id: 'work', nome: 'Trabalho', periodo: '2026.2', horario: '2M2 4M2' };
storage.values.set('ufpb-plan:2026.2', JSON.stringify([row()]));
assert.deepEqual(mixed.load('2026.2'), [row()]);
mixed.save('2026.2', [...mixed.load('2026.2'), commitment]);
assert.deepEqual(mixed.load('2026.2'), [row(), commitment]);
mixed.save('2027.1', [{ ...commitment, periodo: '2027.1' }]);
mixed.save('2026.2', []);
assert.equal(mixed.load('2027.1')[0].nome, 'Trabalho');
const unavailable = createPlanStore({ storage: { getItem() { throw Error('denied'); }, setItem() { throw Error('quota'); } } });
assert.deepEqual(unavailable.load('2026.2'), []);
assert.equal(unavailable.save('2026.2', [commitment]), false);
