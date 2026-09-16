const steps = ['Visit', 'Product view', 'Add to cart', 'Checkout', 'Payment', 'Order'];
const stepsElement = document.querySelector('#steps');
const stateElement = document.querySelector('#journey-state');
const feedbackElement = document.querySelector('#feedback');
const apiStatusElement = document.querySelector('#api-status');
const customerCountElement = document.querySelector('#customer-count');
const customerFeedbackElement = document.querySelector('#customer-feedback');
const customerPreviewElement = document.querySelector('#customer-preview-text');
const customerFileNameElement = document.querySelector('#customer-file-name');
const importButton = document.querySelector('#import-customers');
const customerSearchElement = document.querySelector('#customer-search');
const customerTableBody = document.querySelector('#customer-table-body');
const customerTableSummary = document.querySelector('#customer-table-summary');
let loadedCustomers = [];
let customerPage = 1;
let customerTotalPages = 1;
let currentStep = -1;
let pendingCustomers = [];

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let quoted = false;
  for (const character of text.replace(/^\uFEFF/, '')) {
    if (character === '"') quoted = !quoted;
    else if (character === ',' && !quoted) { row.push(field.trim()); field = ''; }
    else if (character === '\n' && !quoted) { row.push(field.trim()); rows.push(row); row = []; field = ''; }
    else if (character !== '\r') field += character;
  }
  if (field || row.length) { row.push(field.trim()); rows.push(row); }
  const headers = rows.shift();
  return rows.filter((values) => values.some(Boolean)).map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] || ''])));
}

function showCustomerPreview(customers) {
  pendingCustomers = customers;
  customerCountElement.textContent = `${customers.length.toLocaleString()} ready`;
  customerPreviewElement.textContent = customers.slice(0, 4).map((customer) => `${customer.first_name} ${customer.last_name} · ${customer.email}`).join('\n');
  importButton.disabled = customers.length === 0;
}

async function readCustomerCsv(file) {
  showCustomerPreview(parseCsv(await file.text()));
  customerFileNameElement.textContent = file.name;
  customerFeedbackElement.textContent = 'CSV loaded. Review the preview, then import it to CRM.';
}

async function loadBundledCsv() {
  const response = await fetch('/data/customers.csv');
  if (!response.ok) throw new Error('Bundled CSV could not be loaded');
  await readCustomerCsv(new File([await response.blob()], 'customers.csv', { type: 'text/csv' }));
}

async function importCustomers() {
  importButton.disabled = true;
  customerFeedbackElement.textContent = `Importing ${pendingCustomers.length.toLocaleString()} customers...`;
  try {
    for (let start = 0; start < pendingCustomers.length; start += 500) {
      const response = await fetch('/crm/api/customers/bulk', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pendingCustomers.slice(start, start + 500)) });
      if (!response.ok) throw new Error(`CRM rejected batch: ${response.status}`);
      customerFeedbackElement.textContent = `Imported ${Math.min(start + 500, pendingCustomers.length).toLocaleString()} of ${pendingCustomers.length.toLocaleString()} customers.`;
    }
    customerFeedbackElement.textContent = `Imported ${pendingCustomers.length.toLocaleString()} customers. Existing emails were updated safely.`;
    await loadCustomers();
  } catch (error) { customerFeedbackElement.textContent = error.message; importButton.disabled = false; }
}

function renderCustomerTable() {
  customerTableSummary.textContent = `${loadedCustomers.length.toLocaleString()} shown of ${customerTotal.toLocaleString()} customers`;
  if (!loadedCustomers.length) {
    customerTableBody.innerHTML = '<tr><td colspan="5" class="table-message">No customers match this search.</td></tr>';
    return;
  }
  customerTableBody.innerHTML = loadedCustomers.map((customer) => `<tr><td><strong>${customer.first_name} ${customer.last_name}</strong></td><td>${customer.email}</td><td>${customer.city || '-'}, ${customer.country || '-'}</td><td><span class="status-badge ${customer.status === 'inactive' ? 'inactive' : ''}">${customer.status}</span></td><td>${customer.preferred_channel || '-'}</td></tr>`).join('');
  document.querySelector('#customer-page-label').textContent = `Page ${customerPage} of ${customerTotalPages}`;
  document.querySelector('#previous-customers').disabled = customerPage <= 1;
  document.querySelector('#next-customers').disabled = customerPage >= customerTotalPages;
}

async function loadCustomers() {
  customerTableSummary.textContent = 'Loading customers...';
  try {
    const search = encodeURIComponent(customerSearchElement.value.trim());
    const response = await fetch(`/crm/api/customers?page=${customerPage}&page_size=100&search=${search}`);
    if (!response.ok) throw new Error(`CRM rejected customer list: ${response.status}`);
    const result = await response.json();
    loadedCustomers = result.items;
    customerTotal = result.total;
    customerTotalPages = result.total_pages;
    renderCustomerTable();
  } catch (error) {
    customerTableBody.innerHTML = `<tr><td colspan="5" class="table-message">${error.message}</td></tr>`;
    customerTableSummary.textContent = '';
  }
}

function renderSteps() {
  stepsElement.innerHTML = steps.map((step, index) => `<div class="step ${index <= currentStep ? 'done' : ''}"><span class="step-index">${index <= currentStep ? '✓' : String(index + 1).padStart(2, '0')}</span><span>${step}</span></div>`).join('');
}

function advanceJourney(step) {
  currentStep = Math.max(currentStep, step);
  stateElement.textContent = currentStep >= steps.length - 1 ? 'Complete' : 'In progress';
  stateElement.classList.add('active');
  renderSteps();
}

async function startVisit() {
  advanceJourney(1);
  feedbackElement.textContent = 'Product viewed. Select an outcome to continue this controlled journey.';
  try {
    const response = await fetch('/crm/api/health');
    apiStatusElement.textContent = response.ok ? 'CRM connected' : 'CRM unavailable';
  } catch { apiStatusElement.textContent = 'CRM unavailable'; }
}

async function completeOutcome(outcome) {
  advanceJourney(outcome === 'purchase' ? 5 : 3);
  const messages = { purchase: 'Purchase recorded. The simulator is ready for another session.', abandon: 'Cart abandoned. This journey is now an analytical signal.', failure: 'Payment failed. The order was not created.' };
  feedbackElement.textContent = messages[outcome];
  if (outcome === 'purchase') {
    try {
      const response = await fetch('/crm/api/customers');
      const customers = (await response.json()).items;
      if (!customers.length) throw new Error('No customers loaded');
      const customer = customers[Math.floor(Math.random() * customers.length)];
      feedbackElement.textContent = `Purchase recorded for ${customer.first_name} ${customer.last_name}.`;
    } catch { feedbackElement.textContent += ' Load customers from CSV before recording a purchase.'; }
  }
}

document.querySelector('#start-journey').addEventListener('click', startVisit);
document.querySelectorAll('[data-outcome]').forEach((button) => button.addEventListener('click', () => completeOutcome(button.dataset.outcome)));
document.querySelectorAll('[data-tab]').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('[data-tab]').forEach((tab) => tab.classList.toggle('active', tab === button));
  document.querySelectorAll('.view').forEach((view) => { view.hidden = view.id !== `${button.dataset.tab}-view`; });
  if (button.dataset.tab === 'customers') loadCustomers();
}));
document.querySelector('#load-default-csv').addEventListener('click', () => loadBundledCsv().catch((error) => { customerFeedbackElement.textContent = error.message; }));
document.querySelector('#customer-file').addEventListener('change', (event) => { if (event.target.files[0]) readCustomerCsv(event.target.files[0]); });
importButton.addEventListener('click', importCustomers);
let customerTotal = 0;
let searchTimer;
customerSearchElement.addEventListener('input', () => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => { customerPage = 1; loadCustomers(); }, 250);
});
document.querySelector('#refresh-customers').addEventListener('click', loadCustomers);
document.querySelector('#previous-customers').addEventListener('click', () => { if (customerPage > 1) { customerPage -= 1; loadCustomers(); } });
document.querySelector('#next-customers').addEventListener('click', () => { if (customerPage < customerTotalPages) { customerPage += 1; loadCustomers(); } });
renderSteps();