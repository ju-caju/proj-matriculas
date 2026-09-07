/* Sharing UI owns the link and copy intent; persistence stays in PlanStore. */
(function (root) {
  const { $, el } = FrontendDom;
  const S = Schedule;

  function create({ getPlan, store, api, onView, onHome, onLogin, onAuthenticated, onImported, notify }) {
    let active = false, plan = null, copyIntent = false, revision = 0;
    let checking = false, previewLocal = '', authorPlan = null;

    function itemList(selector, items) {
      $(selector).replaceChildren(...items.map(item => el('li', `${S.name(item)} · ${S.label(item)} · ${S.describe(item.horario)}`)));
    }

    function reviewShare() {
      const included = authorPlan.items.filter(item => $('#share-commitments').checked || item.type !== 'commitment');
      $('#share-count').textContent = S.counts(included);
      itemList('#share-items', included);
      $('#share-link').value = '';
      $('#share-result').hidden = true;
      $('#share-error').textContent = '';
    }

    $('#share-plan').addEventListener('click', () => {
      authorPlan = structuredClone(getPlan());
      $('#share-period').textContent = 'Período ' + authorPlan.periodo;
      $('#share-commitments').checked = false;
      $('#native-share').hidden = typeof navigator.share !== 'function';
      reviewShare();
      $('#share-dialog').showModal();
    });
    $('#share-commitments').addEventListener('change', reviewShare);
    $('#close-share').addEventListener('click', () => $('#share-dialog').close());
    $('#generate-share').addEventListener('click', () => {
      try {
        const fragment = SharedPlan.encode(authorPlan.periodo, authorPlan.items, $('#share-commitments').checked);
        $('#share-link').value = location.origin + location.pathname + fragment;
        $('#share-result').hidden = false;
        $('#share-error').textContent = '';
        ($('#native-share').hidden ? $('#copy-share-link') : $('#native-share')).focus();
      } catch (error) { $('#share-error').textContent = error.message; }
    });
    $('#copy-share-link').addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText($('#share-link').value);
        $('#share-error').textContent = 'Link copiado.';
      } catch {
        $('#share-error').textContent = 'Não foi possível acessar a área de transferência. Copie o link do campo acima.';
        $('#share-link').focus(); $('#share-link').select();
      }
    });
    $('#native-share').addEventListener('click', async () => {
      try { await navigator.share({ url: $('#share-link').value }); }
      catch (error) {
        if (error.name !== 'AbortError') $('#share-error').textContent = 'Não foi possível compartilhar pelo dispositivo. Use Copiar link ou copie o campo acima.';
      }
    });

    function readLocation() {
      revision++; copyIntent = false; plan = null;
      $('#merge-dialog').close(); $('#share-dialog').close();
      active = !!location.hash;
      if (!active) { onHome(); return; }
      try { plan = SharedPlan.decode(location.hash); onView(plan); }
      catch (error) { onView(null, error.message); }
    }

    function home() {
      history.replaceState(null, '', location.pathname + location.search);
      readLocation();
    }
    $('#shared-home').addEventListener('click', home);
    $('#shared-error-home').addEventListener('click', home);
    window.addEventListener('hashchange', readLocation);

    function showPreview(local) {
      const preview = SharedPlan.compare(plan, local);
      previewLocal = JSON.stringify(local);
      $('#merge-period').textContent = 'Período ' + plan.periodo;
      $('#merge-additions').textContent = S.counts(preview.additions);
      $('#merge-duplicates').textContent = S.counts(preview.duplicates);
      itemList('#merge-new-list', preview.additions);
      itemList('#merge-duplicate-list', preview.duplicates);
      $('#merge-conflicts').textContent = preview.conflicts.length ? `${preview.conflicts.length} pares de atividades com choque de horário.` : 'Sem choques de horário.';
      $('#merge-conflict-list').replaceChildren(...preview.conflicts.map(conflict => el('li',
        `${S.name(conflict.a)} × ${S.name(conflict.b)} · ${conflict.hits.map(hit => `${S.DAYS[hit.day]} ${S.time(hit.start)}–${S.time(hit.end)}`).join(' / ')}`)));
      $('#merge-error').textContent = '';
      $('#merge-dialog').showModal();
    }

    async function copy(confirm = false) {
      if (!plan || checking) return;
      checking = true; copyIntent = true;
      const started = revision;
      $('#confirm-merge').disabled = true; $('#copy-shared').disabled = true;
      try {
        const session = await api('/api/session');
        if (started !== revision) return;
        onAuthenticated(session.authenticated);
        if (!session.authenticated) {
          $('#merge-dialog').close(); onLogin(); return;
        }
        const local = store.load(plan.periodo);
        if (!confirm) { showPreview(local); return; }
        if (JSON.stringify(local) !== previewLocal) {
          showPreview(local);
          $('#merge-error').textContent = 'Sua grade mudou desde a prévia. Revise os itens e confirme novamente.';
          return;
        }
        const preview = SharedPlan.compare(plan, local), merged = SharedPlan.merge(plan, local);
        if (!store.save(plan.periodo, merged)) {
          $('#merge-error').textContent = PlanStore.SAVE_ERROR; return;
        }
        const periodo = plan.periodo;
        home(); onImported(periodo, merged);
        notify(`Cópia concluída: ${S.counts(preview.additions)} adicionados; ${S.counts(preview.duplicates)} ignorados.`);
      } catch (error) {
        if (started !== revision) return;
        if ($('#merge-dialog').open) $('#merge-error').textContent = error.message;
        else notify(error.message, true);
      } finally {
        checking = false;
        $('#confirm-merge').disabled = false; $('#copy-shared').disabled = false;
      }
    }

    $('#copy-shared').addEventListener('click', () => copy());
    $('#confirm-merge').addEventListener('click', () => copy(true));
    $('#cancel-merge').addEventListener('click', () => { copyIntent = false; revision++; $('#merge-dialog').close(); });
    $('#merge-dialog').addEventListener('cancel', () => { copyIntent = false; revision++; });

    return {
      get active() { return active; },
      start: readLocation,
      refresh() { if (plan) onView(plan); },
      async afterLogin() { if (copyIntent && plan) await copy(); },
    };
  }

  root.ShareUI = { create };
})(globalThis);
