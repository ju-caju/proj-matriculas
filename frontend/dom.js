/* DOM primitives shared by the views.  Domain scheduling stays in schedule.js. */
(function (root) {
  const query = selector => document.querySelector(selector);
  const element = (tag, text, className) => {
    const value = document.createElement(tag);
    if (text !== undefined) value.textContent = text;
    if (className) value.className = className;
    return value;
  };
  const courseName = row => row.disciplina.replace(/\s*\(GRADUAÇÃO\)\s*$/i, '');
  const courseColor = row => 'color-' + ([...row.disciplina].reduce(
    (number, character) => (number * 31 + character.charCodeAt(0)) >>> 0, 0
  ) % 6);
  root.FrontendDom = { $: query, el: element, name: courseName, color: courseColor };
})(globalThis);
