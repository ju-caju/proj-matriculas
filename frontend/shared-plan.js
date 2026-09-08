/* Versioned, browser-only snapshots. Never pass fragments to the API. */
(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) module.exports = factory(require('../schedule.js'));
  else root.SharedPlan = factory(root.Schedule);
})(globalThis, function (S) {
  const COURSE_FIELDS = ['disciplina', 'periodo', 'turma', 'docente', 'tipo', 'forma', 'horario', 'local'];
  const COMMITMENT_FIELDS = ['type', 'nome', 'periodo', 'horario'];
  const PREFIX = '#grade=';
  const COMPACT_VERSION = 2;
  const LIMITS = Object.freeze({ items: 40, field: 240, horario: 1000, fragment: 16000 });
  const invalid = () => new Error('Link de grade inválido. Confira o link completo ou volte ao início.');
  const tooLarge = () => new Error('A grade excede o limite do link. Reduza os itens ou o tamanho dos campos.');
  const periodValid = value => typeof value === 'string' && /^20\d{2}\.[0-4]$/.test(value);

  function exactFields(value, fields) {
    if (!value || typeof value !== 'object' || Array.isArray(value) ||
        Object.keys(value).length !== fields.length || !fields.every(field => Object.hasOwn(value, field))) throw invalid();
  }

  function serialize(plan) {
    const bytes = new TextEncoder().encode(JSON.stringify(plan));
    // Bound before allocating the base64 string or spreading bytes.
    if (bytes.length > LIMITS.fragment) throw tooLarge();
    const fragment = PREFIX + btoa(String.fromCharCode(...bytes)).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
    if (fragment.length > LIMITS.fragment) throw tooLarge();
    return fragment;
  }

  function validate(plan) {
    exactFields(plan, ['version', 'periodo', 'items']);
    if (plan.version !== 1 || !periodValid(plan.periodo) || !Array.isArray(plan.items)) throw invalid();
    if (!plan.items.length) throw new Error('Nenhum item para compartilhar. Inclua compromissos pessoais ou adicione uma turma.');
    if (plan.items.length > LIMITS.items) throw tooLarge();
    for (const item of plan.items) {
      const fields = item?.type === 'commitment' ? COMMITMENT_FIELDS : COURSE_FIELDS;
      exactFields(item, fields);
      for (const field of fields) {
        if (typeof item[field] !== 'string' || /[\u0000-\u001f\u007f]/.test(item[field])) throw invalid();
        if (item[field].length > (field === 'horario' ? LIMITS.horario : LIMITS.field)) throw tooLarge();
      }
      if (item.periodo !== plan.periodo || !(item.type === 'commitment' ? item.nome.trim() : item.disciplina.trim() && item.turma.trim())) throw invalid();
      if (S.parse(item.horario).errors.length || (item.type === 'commitment' &&
          !/^[1-7]+[MTN][1-6]+(?:\s+[1-7]+[MTN][1-6]+)*$/i.test(item.horario))) {
        throw new Error('Há horário não reconhecido na grade. Revise os itens antes de compartilhar.');
      }
    }
    serialize(plan);
    return plan;
  }

  function encode(periodo, items, includeCommitments = false) {
    const snapshot = { version: 1, periodo, items: items
      .filter(item => includeCommitments || item.type !== 'commitment')
      .map(item => Object.fromEntries((item.type === 'commitment' ? COMMITMENT_FIELDS : COURSE_FIELDS)
        .map(field => [field, item[field]]))) };
    validate(snapshot);
    const compact = [COMPACT_VERSION, periodo, snapshot.items.map(item => item.type === 'commitment'
      ? [1, item.nome, item.horario]
      : [0, item.disciplina, item.turma, item.docente, item.tipo, item.forma, item.horario, item.local])];
    return serialize(compact);
  }

  function expandCompact(value) {
    if (!Array.isArray(value) || value.length !== 3 || value[0] !== COMPACT_VERSION || !Array.isArray(value[2])) throw invalid();
    const periodo = value[1];
    return { version: 1, periodo, items: value[2].map(item => {
      if (!Array.isArray(item)) throw invalid();
      if (item[0] === 0 && item.length === 8) {
        return {
          disciplina: item[1], periodo, turma: item[2], docente: item[3], tipo: item[4],
          forma: item[5], horario: item[6], local: item[7],
        };
      }
      if (item[0] === 1 && item.length === 3) return { type: 'commitment', nome: item[1], periodo, horario: item[2] };
      throw invalid();
    }) };
  }

  function decode(fragment) {
    if (typeof fragment !== 'string' || !fragment.startsWith(PREFIX)) throw invalid();
    if (fragment.length > LIMITS.fragment) throw tooLarge();
    const payload = fragment.slice(PREFIX.length);
    if (!/^[A-Za-z0-9_-]+$/.test(payload)) throw invalid();
    let plan;
    try {
      const binary = atob(payload.replaceAll('-', '+').replaceAll('_', '/'));
      if (btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '') !== payload) throw invalid();
      const value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Uint8Array.from(binary, char => char.charCodeAt(0))));
      plan = Array.isArray(value) ? expandCompact(value) : value;
    } catch { throw invalid(); }
    return validate(plan);
  }

  function commitmentHours(horario) {
    const codes = new Set();
    for (const meeting of S.parse(horario).meetings) {
      for (const [shift, slots] of Object.entries(S.TIMES)) slots.forEach(([start, end], index) => {
        if (start >= meeting.start && end <= meeting.end) codes.add(`${meeting.day}${shift}${index + 1}`);
      });
    }
    return [...codes].sort().join(' ');
  }

  function identity(item) {
    return item.type === 'commitment'
      ? JSON.stringify([item.periodo, 'commitment', item.nome.normalize('NFC').trim().replace(/\s+/gu, ' ').toLocaleLowerCase('pt-BR'), commitmentHours(item.horario)])
      : S.key(item);
  }

  function compare(plan, local) {
    validate(plan);
    const current = local.filter(item => item.periodo === plan.periodo);
    const seen = new Set(current.map(identity)), additions = [], duplicates = [];
    for (const item of plan.items) {
      const key = identity(item);
      if (seen.has(key)) duplicates.push(item);
      else { seen.add(key); additions.push(item); }
    }
    return { additions, duplicates, conflicts: S.conflicts([...current, ...additions]) };
  }

  function merge(plan, local) {
    const { additions } = compare(plan, local);
    return [...local.filter(item => item.periodo === plan.periodo), ...additions.map(item => item.type === 'commitment'
      ? { ...item, id: crypto.randomUUID(), horario: commitmentHours(item.horario) }
      : { ...item })];
  }

  return { encode, decode, validate, compare, merge, LIMITS };
});
