/* Browser-only persistence for the planner.  The server never receives this data. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PlanStore = api;
})(globalThis, function () {
  function createPlanStore({ storage, key }) {
    const readStorage = storage || globalThis.localStorage;
    const identify = key || (value => JSON.stringify([
      value.periodo,
      value.disciplina,
      value.turma,
      value.horario,
    ]));

    function valid(value) {
      return value && typeof value === 'object' &&
        typeof value.periodo === 'string' &&
        typeof value.disciplina === 'string' &&
        typeof value.turma === 'string' &&
        typeof value.horario === 'string';
    }

    function load(semester) {
      try {
        const parsed = JSON.parse(readStorage.getItem('ufpb-plan:' + semester) || '[]');
        if (!Array.isArray(parsed)) return [];
        const unique = new Map();
        for (const value of parsed) {
          if (valid(value) && value.periodo === semester) unique.set(identify(value), value);
        }
        return [...unique.values()];
      } catch {
        return [];
      }
    }

    function save(semester, values) {
      try {
        readStorage.setItem('ufpb-plan:' + semester, JSON.stringify(
          values.filter(value => valid(value) && value.periodo === semester)
        ));
        return true;
      } catch {
        return false;
      }
    }

    return { load, save };
  }

  return { createPlanStore };
});
