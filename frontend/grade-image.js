// Canvas export is isolated from the DOM planner so it can be tested independently.
(function (root) {
  const S = root.Schedule;
  const name = row => row.disciplina.replace(/\s*\(GRADUAÇÃO\)\s*$/i, '');
  const color = row => 'color-' + ([...row.disciplina].reduce(
    (number, character) => (number * 31 + character.charCodeAt(0)) >>> 0, 0
  ) % 6);

  function gradeImage(courses, term) {
    const days = [2, 3, 4, 5, 6, 7];
    if (courses.some(row => S.parse(row.horario).meetings.some(meeting => meeting.day === 1))) {
      days.push(1);
    }
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    const width = 1500, margin = 40, axis = 76, top = 154, gridHeight = 1104;
    const column = (width - 2 * margin - axis) / days.length;
    const clashes = S.conflicts(courses);
    const unknown = courses.some(row => S.parse(row.horario).errors.length);
    const font = (size, bold = false) => {
      context.font = `${bold ? '600' : '400'} ${size}px Calibri, sans-serif`;
    };
    function wrap(value, maxWidth) {
      const lines = [];
      let line = '';
      for (const word of String(value).split(/\s+/)) {
        if (context.measureText(line ? line + ' ' + word : word).width > maxWidth && line) {
          lines.push(line);
          line = '';
        }
        for (const character of word) {
          if (context.measureText(line + character).width > maxWidth && line) {
            lines.push(line);
            line = '';
          }
          line += character;
        }
        line += ' ';
      }
      if (line.trim()) lines.push(line.trim());
      return lines;
    }
    font(18, true);
    const legends = courses.map((row, index) => {
      font(18, true);
      const title = wrap(`${index + 1}. ${name(row)} · ${row.turma}`, width - 2 * margin - 28);
      font(16);
      const details = wrap(
        `${S.describe(row.horario)} · ${row.docente || ''} · ${row.local || ''} · ${row.horario}`,
        width - 2 * margin - 28
      );
      return { row, title, details, height: title.length * 23 + details.length * 21 + 24 };
    });
    const conflictLines = [];
    font(16);
    for (const conflict of clashes) {
      conflictLines.push(...wrap(
        `Choque: ${courses.indexOf(conflict.a) + 1} × ${courses.indexOf(conflict.b) + 1} — ` +
        conflict.hits.map(hit => `${S.DAYS[hit.day]} ${S.time(hit.start)}–${S.time(hit.end)}`).join('; '),
        width - 2 * margin
      ));
    }
    const height = top + gridHeight + 64 + legends.reduce(
      (total, legend) => total + legend.height, 0
    ) + conflictLines.length * 23 + 60;
    canvas.width = width * 2;
    canvas.height = height * 2;
    context.scale(2, 2);
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, width, height);
    context.textBaseline = 'top';
    const text = (value, x, y, size = 16, bold = false, textColor = '#292524') => {
      font(size, bold);
      context.fillStyle = textColor;
      context.fillText(value, x, y);
    };
    text('Minha grade · UFPB', margin, 30, 30, true);
    text(`${term} · ${courses.length} turmas`, margin, 72, 19);
    text(
      unknown ? 'Há horários não reconhecidos: confira os detalhes abaixo.' :
        clashes.length ? `${clashes.length} par(es) de turmas com choque de horário` :
          'Sem choques de horário',
      margin, 103, 16, false, clashes.length || unknown ? '#a32620' : '#365d3f'
    );
    context.fillStyle = '#f4f1ec';
    context.fillRect(margin, top - 32, width - 2 * margin, 32);
    days.forEach((day, index) => text(S.DAYS[day], margin + axis + index * column + 10, top - 25, 16, true));
    for (let minutes = 420; minutes <= 1320; minutes += 60) {
      const y = top + (minutes - 420) / 920 * gridHeight;
      context.strokeStyle = '#e5e0d8';
      context.beginPath();
      context.moveTo(margin + axis, y);
      context.lineTo(width - margin, y);
      context.stroke();
      text(S.time(minutes), margin + 8, y + 3, 13);
    }
    for (let index = 0; index <= days.length; index++) {
      const x = margin + axis + index * column;
      context.strokeStyle = '#dedbd5';
      context.beginPath();
      context.moveTo(x, top);
      context.lineTo(x, top + gridHeight);
      context.stroke();
    }
    const palette = [
      ['#e9efe3', '#708450'], ['#f4e9d7', '#a17b3d'], ['#ece5f2', '#9477aa'],
      ['#e0efeb', '#548c7d'], ['#f1e2e8', '#a57286'], ['#e9e7de', '#8a8466'],
    ];
    days.forEach((day, dayIndex) => {
      const events = courses.flatMap((row, index) => S.parse(row.horario).meetings
        .filter(meeting => meeting.day === day)
        .map(meeting => ({ ...meeting, row, index })));
      for (const event of S.layout(events)) {
        const clash = courses.some(row => S.key(row) !== S.key(event.row) &&
          S.parse(row.horario).meetings.some(meeting => S.overlap(event, meeting)));
        const [background, border] = clash ? ['#ffe5e0', '#bc3f35'] :
          palette[Number(color(event.row).slice(-1))];
        const x = margin + axis + dayIndex * column + event.lane / event.lanes * column + 3;
        const y = top + (event.start - 420) / 920 * gridHeight + 2;
        const blockWidth = column / event.lanes - 6;
        const blockHeight = (event.end - event.start) / 920 * gridHeight - 4;
        context.fillStyle = background;
        context.fillRect(x, y, blockWidth, blockHeight);
        context.strokeStyle = border;
        context.strokeRect(x, y, blockWidth, blockHeight);
        context.save();
        context.beginPath();
        context.rect(x + 4, y + 3, Math.max(0, blockWidth - 8), blockHeight - 6);
        context.clip();
        text(`${event.index + 1}${clash ? ' · CHOQUE' : ''}`, x + 7, y + 6, 13, true, clash ? '#a32620' : '#292524');
        font(14, true);
        const lines = wrap(name(event.row), Math.max(10, blockWidth - 14));
        const maxLines = Math.max(1, Math.floor((blockHeight - 56) / 17));
        lines.slice(0, maxLines).forEach((line, index) => text(
          line + (index === maxLines - 1 && lines.length > maxLines ? '…' : ''),
          x + 7, y + 26 + index * 17, 14, true
        ));
        text(`${S.time(event.start)}–${S.time(event.end)}`, x + 7, y + blockHeight - 22, 12);
        context.restore();
      }
    });
    let y = top + gridHeight + 30;
    text('Disciplinas e horários', margin, y, 22, true);
    y += 34;
    for (const entry of legends) {
      const [, border] = palette[Number(color(entry.row).slice(-1))];
      context.fillStyle = border;
      context.fillRect(margin, y, 4, entry.height - 16);
      for (const line of entry.title) { text(line, margin + 16, y, 18, true); y += 23; }
      for (const line of entry.details) { text(line, margin + 16, y, 16); y += 21; }
      y += 24;
    }
    for (const line of conflictLines) { text(line, margin, y, 16, false, '#a32620'); y += 23; }
    text('Planejamento pessoal · não substitui a matrícula no SIGAA.', margin, y + 16, 14, false, '#71675d');
    return canvas;
  }

  root.GradeImage = { render: gradeImage };
})(globalThis);
