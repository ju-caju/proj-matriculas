const assert = require('node:assert/strict');
const Schedule = require('../schedule.js');
const CourseFilter = require('./course-filter.js');

const rows = [
  { disciplina: 'CÁLCULO', docente: 'ANA', horario: '24M23' },
  { disciplina: 'FÍSICA', docente: 'BRUNO', horario: '35T45' },
  { disciplina: 'ALGORITMOS', docente: 'CARLA', horario: '6N12' },
  { disciplina: 'PROJETO INTEGRADO', docente: 'DAVI', horario: '2M1 4N1' },
];

assert.deepEqual(CourseFilter.filter(rows, '', 'morning', Schedule), [rows[0], rows[3]]);
assert.deepEqual(CourseFilter.filter(rows, '', 'afternoon', Schedule), [rows[1]]);
assert.deepEqual(CourseFilter.filter(rows, '', 'evening', Schedule), [rows[2], rows[3]]);
assert.deepEqual(CourseFilter.filter(rows, 'calculo', '', Schedule), [rows[0]]);
assert.deepEqual(CourseFilter.filter(rows, 'carla', 'evening', Schedule), [rows[2]]);
assert.deepEqual(CourseFilter.filter(rows, 'fisica', 'morning', Schedule), []);

console.log('Filtro de turmas: OK');
