(function (root) {
  const normalize = value => String(value).normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '').toLowerCase();

  function inShift(meeting, shift) {
    if (shift === 'morning') return meeting.start < 12 * 60;
    if (shift === 'afternoon') return meeting.start >= 12 * 60 && meeting.start < 19 * 60;
    if (shift === 'evening') return meeting.start >= 19 * 60;
    return true;
  }

  function filter(rows, search, shift, schedule) {
    const term = normalize(search);
    return rows.filter(row => {
      const matchesSearch = normalize(Object.values(row).join(' ')).includes(term);
      const matchesShift = !shift || schedule.parse(row.horario).meetings
        .some(meeting => inShift(meeting, shift));
      return matchesSearch && matchesShift;
    });
  }

  const api = { filter };
  root.CourseFilter = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(globalThis);
