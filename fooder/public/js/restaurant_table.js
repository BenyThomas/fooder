frappe.ui.form.on('Restaurant Table', {
  refresh(frm) {
    if (frm.is_new()) {
      return;
    }

    frm.page.set_primary_action(__('Regenerate QR'), () => {
      frappe.confirm(
        __('This will disable the current QR token and generate a new one. Continue?'),
        () => regenerateToken(frm)
      );
    });

    frm.add_custom_button(__('Disable QR'), () => {
      frappe.confirm(
        __('This will disable the active QR token. Continue?'),
        () => disableToken(frm)
      );
    }, __('QR Actions'));

    loadQrInfo(frm);
  },
});

function renderQrHeadline(frm, data) {
  const active = data?.active;
  if (!active) {
    frm.dashboard.set_headline(__('No active QR token for this table.'));
    return;
  }

  const link = `<a href="${active.qr_url}" target="_blank">${active.qr_url}</a>`;
  const tokenLine = active.token ? `<div>${__('Token')}: ${active.token}</div>` : '';
  frm.dashboard.set_headline(`
    <div style="display:flex;flex-direction:column;gap:4px;">
      <div style="font-weight:600;">${__('Guest Ordering URL')}: ${link}</div>
      ${tokenLine}
    </div>
  `);
}

function renderHistory(frm, data) {
  const history = data?.history || [];
  if (!history.length) {
    return;
  }

  const rows = history
    .map((row) => {
      const status = row.is_enabled ? __('Active') : __('Disabled');
      return `<tr><td>${row.token}</td><td>${status}</td><td>${row.creation}</td></tr>`;
    })
    .join('');

  frm.dashboard.add_section(`
    <div class="form-section" style="margin-top:8px;">
      <div class="section-head">${__('QR Token History')}</div>
      <div class="section-body">
        <table class="table table-bordered">
          <thead><tr><th>${__('Token')}</th><th>${__('Status')}</th><th>${__('Created')}</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `);
}

function loadQrInfo(frm) {
  frappe.call({
    method: 'fooder.integrations.restaurant_table_events.get_table_qr_info',
    args: { restaurant_table: frm.doc.name },
    callback: (r) => {
      frm.dashboard.clear_comment();
      frm.dashboard.reset_headline();
      frm.dashboard.body.empty();
      renderQrHeadline(frm, r.message);
      renderHistory(frm, r.message);
      frm.refresh_fields();
    },
  });
}

function regenerateToken(frm) {
  frappe.call({
    method: 'fooder.integrations.restaurant_table_events.regenerate_table_qr',
    args: { restaurant_table: frm.doc.name },
    callback: (r) => {
      if (r.exc) return;
      frappe.show_alert({ message: __('QR token regenerated'), indicator: 'green' });
      loadQrInfo(frm);
    },
  });
}

function disableToken(frm) {
  frappe.call({
    method: 'fooder.integrations.restaurant_table_events.disable_table_qr',
    args: { restaurant_table: frm.doc.name },
    callback: (r) => {
      if (r.exc) return;
      frappe.show_alert({ message: __('QR token disabled'), indicator: 'orange' });
      loadQrInfo(frm);
    },
  });
}
