// Search form + per-row Generate Deck / Send Outreach buttons.

(function () {
  const searchForm = document.getElementById('search-form');
  if (searchForm) {
    searchForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const input = document.getElementById('search-input');
      const btn = searchForm.querySelector('button[type=submit]');
      const query = input.value.trim();
      if (!query) return;
      btn.disabled = true;
      const originalLabel = btn.textContent;
      btn.textContent = 'Searching…';
      try {
        const res = await fetch('/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query }),
        });
        const data = await res.json();
        if (data.ok) {
          window.location.reload();
        } else {
          alert('Search failed: ' + (data.error || 'unknown error'));
        }
      } catch (err) {
        alert('Search failed: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = originalLabel;
      }
    });
  }

  function bindRowAction(selector, urlBuilder, onSuccess) {
    document.querySelectorAll(selector).forEach((btn) => {
      btn.addEventListener('click', async () => {
        const row = btn.closest('tr');
        const rowId = row.dataset.row;
        btn.disabled = true;
        const originalLabel = btn.textContent;
        btn.textContent = 'Working…';
        row.classList.add('row-loading');
        try {
          const res = await fetch(urlBuilder(rowId), { method: 'POST' });
          const data = await res.json();
          if (data.ok) {
            onSuccess(row, data);
          } else {
            alert('Failed: ' + (data.error || 'unknown error'));
            btn.disabled = false;
            btn.textContent = originalLabel;
          }
        } catch (err) {
          alert('Failed: ' + err.message);
          btn.disabled = false;
          btn.textContent = originalLabel;
        } finally {
          row.classList.remove('row-loading');
        }
      });
    });
  }

  bindRowAction(
    '.js-gen-deck',
    (rowId) => `/generate-deck/${rowId}`,
    (row) => {
      row.querySelector('.cell-deck').innerHTML = '<span class="badge badge-done">Ready</span>';
    }
  );

  bindRowAction(
    '.js-send-outreach',
    (rowId) => `/send-outreach/${rowId}`,
    (row, data) => {
      if (data.whatsapp_url) {
        const opened = window.open(data.whatsapp_url, '_blank');
        if (!opened) {
          alert('Popup blocked. Open this link manually:\n\n' + data.whatsapp_url);
        }
      }
      const cell = row.querySelector('.cell-outreach');
      cell.innerHTML = '';
      const link = document.createElement('a');
      link.href = data.whatsapp_url || '#';
      link.target = '_blank';
      link.rel = 'noopener';
      link.className = 'badge badge-done';
      link.style.textDecoration = 'none';
      link.textContent = '↗ Open WhatsApp';
      cell.appendChild(link);
      const statusCell = row.querySelector('.cell-status');
      if (statusCell) statusCell.innerHTML = '<span class="status status-contacted">Contacted</span>';
    }
  );
})();
