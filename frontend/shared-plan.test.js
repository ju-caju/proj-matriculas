const assert = require('node:assert/strict');
const { test } = require('node:test');
const SharedPlan = require('./shared-plan.js');

const course = { disciplina: 'CÁLCULO', periodo: '2026.2', turma: '01', docente: 'DOCENTE', tipo: 'REGULAR', forma: 'Presencial', horario: '24M23', local: 'SALA', vagas: '10', situacao: 'ABERTA', autor: 'privado' };
const commitment = { type: 'commitment', id: 'identidade-do-autor', nome: 'Estágio', periodo: '2026.2', horario: '2M2 4M2' };
const rawFragment = value => '#grade=' + Buffer.from(JSON.stringify(value)).toString('base64url');

test('link contém fotografia das turmas e exclui compromissos e campos privados por padrão', () => {
  const fragment = SharedPlan.encode('2026.2', [course, commitment]);
  const plan = SharedPlan.decode(fragment);
  assert.deepEqual(plan, { version: 1, periodo: '2026.2', items: [{ disciplina: 'CÁLCULO', periodo: '2026.2', turma: '01', docente: 'DOCENTE', tipo: 'REGULAR', forma: 'Presencial', horario: '24M23', local: 'SALA' }] });
  assert.equal(plan.items[0].vagas, undefined);
  assert.equal(plan.items[0].autor, undefined);
  const changed = { ...course, turma: '02' };
  SharedPlan.encode('2026.2', [changed]);
  assert.equal(SharedPlan.decode(fragment).items[0].turma, '01');
});

test('prévia preserva a grade, separa duplicatas e cria identidades locais apenas para novos compromissos', () => {
  const local = [course, { ...commitment, id: 'local', nome: '  ESTÁGIO  ', horario: '4M2 2M2' }];
  const otherName = { ...commitment, nome: 'Trabalho' };
  const otherTime = { ...commitment, horario: '3N1' };
  const shared = SharedPlan.decode(SharedPlan.encode('2026.2', [course, commitment, otherName, otherTime, otherName], true));
  const before = JSON.stringify(local);
  const preview = SharedPlan.compare(shared, local);
  assert.equal(preview.duplicates.length, 3);
  assert.deepEqual(preview.additions.map(item => item.nome), ['Trabalho', 'Estágio']);
  assert.equal(preview.conflicts.length, 3);
  assert.equal(JSON.stringify(local), before);
  const merged = SharedPlan.merge(shared, local);
  assert.equal(merged.length, 4);
  assert.deepEqual(merged.slice(0,2), local);
  assert.equal(merged[2].horario, '2M2 4M2');
  assert.ok(merged[2].id);
  assert.notEqual(merged[2].id, commitment.id);
  assert.notEqual(merged[2].id, merged[3].id);
  assert.deepEqual(SharedPlan.merge(shared, merged), merged);
  assert.equal(SharedPlan.compare(shared, [{ ...course, periodo: '2026.1' }]).additions.length, 4);
  const equivalent = SharedPlan.decode(SharedPlan.encode('2026.2', [{ ...commitment, horario: '42M23' }], true));
  assert.equal(SharedPlan.compare(equivalent, [{ ...commitment, horario: '4M3 2M3 4M2 2M2' }]).additions.length, 0);
});

test('valida a grade inteira na geração e leitura, com limites e contrato fechado', () => {
  const good = SharedPlan.decode(SharedPlan.encode('2026.2', [course, commitment], true));
  assert.equal(good.items.length, 2);
  assert.equal(good.items[1].id, undefined);
  const invalid = [
    null, [], {}, { ...good, version: 2 }, { ...good, version: '1' },
    { ...good, autor: 'alguém' }, { ...good, periodo: '2026.9' },
    { ...good, periodo: '1999.1' }, { ...good, items: [] },
    { ...good, items: {} }, { ...good, items: Array(41).fill(good.items[0]) },
    ...[
      null, [], { ...good.items[0], vagas: '10' },
      { ...good.items[0], disciplina: undefined }, { ...good.items[0], docente: 7 },
      { ...good.items[0], periodo: '2026.1' }, { ...good.items[0], horario: '2N6' },
      { ...good.items[0], horario: '24M23 incompleto' },
      { ...good.items[0], disciplina: 'a'.repeat(241) },
      { ...good.items[0], horario: '2M1 '.repeat(251) },
      { ...good.items[0], turma: '' }, { ...good.items[0], type: 'unknown' },
      { ...good.items[1], nome: '  ' }, { ...good.items[1], id: 'autor' },
      { ...good.items[1], horario: '2M1 (01/01/2026 - 31/12/2026)' },
    ].map(item => ({ ...good, items: [good.items[0], item] })),
  ];
  for (const plan of invalid) {
    assert.throws(() => SharedPlan.validate(plan));
    assert.throws(() => SharedPlan.decode(rawFragment(plan)));
  }
  for (const fragment of ['#other=abc', '#grade=', '#grade=!!!', '#grade=a', '#grade=ew', '#grade=_w', rawFragment(good).slice(0,-5), '#grade='+'a'.repeat(16000)]) {
    assert.throws(() => SharedPlan.decode(fragment));
  }
  assert.throws(() => SharedPlan.encode('2026.2', [commitment]), /compromissos/i);
  assert.equal(SharedPlan.decode(SharedPlan.encode('2026.2', [commitment], true)).items.length, 1);
  assert.throws(() => SharedPlan.encode('2026.2', [{ ...course, horario: 'inválido' }]), /horário/i);
  assert.throws(() => SharedPlan.encode('2026.2', Array(41).fill(course)), /limite/i);
  const large = Array.from({ length: 40 }, (_, i) => ({ ...course, turma: String(i), docente: 'á'.repeat(240) }));
  assert.throws(() => SharedPlan.encode('2026.2', large), /limite/i);
  assert.throws(() => SharedPlan.decode(rawFragment({ ...good, items: large.map(({ vagas, situacao, autor, ...item }) => item) })), /limite/i);
  assert.equal(SharedPlan.decode(SharedPlan.encode('2026.2', [course, { ...commitment, horario: 'inválido' }])).items.length, 1);
});
