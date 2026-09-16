const steps = ['Visit', 'Product view', 'Add to cart', 'Checkout', 'Payment', 'Order'];
const stepsElement = document.querySelector('#steps');
const stateElement = document.querySelector('#journey-state');
const feedbackElement = document.querySelector('#feedback');
const apiStatusElement = document.querySelector('#api-status');
const customerSelect = document.querySelector('#journey-customer');
const storeSelect = document.querySelector('#journey-store');
const productSelect = document.querySelector('#journey-products');
const deliverySelect = document.querySelector('#journey-delivery');
const catalogStoreFilter = document.querySelector('#catalog-store-filter');
let loadedCustomers = [];
let catalog = [];
let activeCart = null;
let activeOrder = null;
let currentStep = -1;
let pendingCustomers = [];
let pendingCatalog = [];
let customerPage = 1;
let customerTotalPages = 1;
let customerTotal = 0;

const api = async (service, path, options = {}) => {
  const response = await fetch(`/${service}${path}`, { headers: { 'Content-Type': 'application/json' }, ...options });
  if (!response.ok) throw new Error(`${service} rejected request: ${response.status}`);
  return response.status === 204 ? null : response.json();
};

function renderSteps() {
  stepsElement.innerHTML = steps.map((step, index) => `<div class="step ${index <= currentStep ? 'done' : ''}"><span class="step-index">${index <= currentStep ? '✓' : String(index + 1).padStart(2, '0')}</span><span>${step}</span></div>`).join('');
}

function advanceJourney(step) {
  currentStep = Math.max(currentStep, step);
  stateElement.textContent = currentStep >= steps.length - 1 ? 'Complete' : 'In progress';
  stateElement.classList.add('active');
  renderSteps();
}

function selectedProducts() {
  return [...productSelect.selectedOptions].map((option) => catalog.find((item) => item.product_id === option.value)).filter(Boolean);
}

function renderJourneyCustomers() {
  customerSelect.innerHTML = loadedCustomers.map((customer) => `<option value="${customer.customer_id}">${customer.first_name} ${customer.last_name} · ${customer.email}</option>`).join('') || '<option value="">Load customers first</option>';
}

function renderCatalog() {
  productSelect.innerHTML = catalog.map((item) => `<option value="${item.product_id}">${item.name} · ${item.currency} ${item.price_amount} · ${item.available_quantity} available</option>`).join('') || '<option value="">No products in this store</option>';
}

async function seedCatalog() {
  const stores = await api('product', '/api/stores');
  let store = stores[0];
  if (!store) store = await api('product', '/api/stores', { method: 'POST', body: JSON.stringify({ name: 'Northstar Central', channel: 'both', city: 'London', country: 'GB' }) });
  let products = await api('product', '/api/products');
  if (!products.length) {
    for (const [sku, name, description] of [['SKU-KETTLE', 'Orbit kettle', 'Precise pour-over kettle'], ['SKU-MUG', 'Field mug', 'Stoneware travel mug'], ['SKU-GRINDER', 'Quiet grinder', 'Compact burr grinder']]) await api('product', '/api/products', { method: 'POST', body: JSON.stringify({ sku, name, description, brand: 'Northstar' }) });
    products = await api('product', '/api/products');
  }
  const existingCatalog = await api('product', `/api/stores/${store.store_id}/catalog`);
  const inventory = await api('product', `/api/stores/${store.store_id}/inventory`);
  for (const product of products) {
    if (!existingCatalog.some((entry) => entry.product_id === product.product_id)) await api('product', `/api/stores/${store.store_id}/catalog`, { method: 'POST', body: JSON.stringify({ product_id: product.product_id, price_amount: 25 + products.indexOf(product) * 15, currency: 'USD' }) });
    if (!inventory.some((entry) => entry.product_id === product.product_id)) await api('product', `/api/stores/${store.store_id}/inventory`, { method: 'POST', body: JSON.stringify({ product_id: product.product_id, quantity: 100 }) });
  }
  return store;
}

async function loadStoreCatalog() {
  const entries = await api('product', `/api/stores/${storeSelect.value}/catalog`);
  const inventory = await api('product', `/api/stores/${storeSelect.value}/inventory`);
  const products = await api('product', '/api/products');
  catalog = entries.map((entry) => {
    const stock = inventory.find((item) => item.product_id === entry.product_id);
    return { ...entry, ...products.find((product) => product.product_id === entry.product_id), available_quantity: stock ? stock.quantity - stock.reserved_quantity : 0 };
  }).filter((item) => item.status === 'active' && item.available_quantity > 0);
  renderCatalog();
}

async function loadJourneyData() {
  try {
    const result = await api('crm', '/api/customers?page=1&page_size=100');
    loadedCustomers = result.items;
    renderJourneyCustomers();
    const store = await seedCatalog();
    const stores = await api('product', '/api/stores');
    storeSelect.innerHTML = stores.map((item) => `<option value="${item.store_id}">${item.name} · ${item.city || item.channel}</option>`).join('');
    storeSelect.value = store.store_id;
    await loadStoreCatalog();
    apiStatusElement.textContent = 'CRM · Product · Shopping connected';
  } catch (error) {
    feedbackElement.textContent = `${error.message}. Start services with ./run.sh.`;
    apiStatusElement.textContent = 'Service unavailable';
  }
}

async function loadCatalogDirectory() {
  const stores = await api('product', '/api/stores');
  const products = await api('product', '/api/products');
  const selectedStore = catalogStoreFilter.value;
  catalogStoreFilter.innerHTML = '<option value="">All stores</option>' + stores.map((store) => `<option value="${store.store_id}">${store.name} · ${store.city || store.channel}</option>`).join('');
  catalogStoreFilter.value = stores.some((store) => store.store_id === selectedStore) ? selectedStore : '';
  const visibleStores = catalogStoreFilter.value ? stores.filter((store) => store.store_id === catalogStoreFilter.value) : stores;
  const rows = (await Promise.all(visibleStores.map(async (store) => {
    const [entries, inventory] = await Promise.all([api('product', `/api/stores/${store.store_id}/catalog`), api('product', `/api/stores/${store.store_id}/inventory`)]);
    return entries.map((entry) => {
      const product = products.find((item) => item.product_id === entry.product_id) || {};
      const stock = inventory.find((item) => item.product_id === entry.product_id);
      return { ...entry, product, store, available: stock ? Math.max(0, stock.quantity - stock.reserved_quantity) : 0 };
    });
  }))).flat();
  document.querySelector('#catalog-directory-count').textContent = `${rows.length.toLocaleString()} products`;
  document.querySelector('#catalog-table-body').innerHTML = rows.map((row) => `<tr><td><strong>${row.product.name || 'Unknown product'}</strong></td><td>${row.product.sku || '-'}</td><td>${row.store.name}</td><td>${row.currency} ${Number(row.price_amount).toFixed(2)}</td><td>${row.available}</td><td>${row.status}</td></tr>`).join('') || '<tr><td colspan="6" class="table-message">No catalog entries found.</td></tr>';
}

function normalizeStoreChannel(value) {
  const channel = (value || 'physical').trim().toLowerCase();
  return { store: 'physical', retail: 'physical', web: 'online', ecommerce: 'online', omnichannel: 'both' }[channel] || channel;
}

function validateCatalogRows(rows) {
  const currencyByCountry = { US: 'USD', CA: 'CAD', GB: 'GBP', FR: 'EUR', DE: 'EUR', IN: 'INR', JP: 'JPY', AU: 'AUD' };
  const stores = new Map(); const products = new Map(); const entries = new Set();
  for (const [index, row] of rows.entries()) {
    const line = index + 2; const country = (row.country || '').trim().toUpperCase(); const currency = (row.currency || '').trim().toUpperCase();
    const sku = (row.sku || '').trim().toUpperCase(); const storeName = (row.store_name || '').trim();
    if (!/^SKU-[A-Z]{2}-\d{5}$/.test(sku)) return `Catalog row ${line}: SKU must match SKU-CC-NNNNN.`;
    if (sku.slice(4, 6) !== country) return `Catalog row ${line}: SKU country ${sku.slice(4, 6)} does not match ${country}.`;
    if (currencyByCountry[country] && currency !== currencyByCountry[country]) return `Catalog row ${line}: ${country} stores must use ${currencyByCountry[country]}, not ${currency}.`;
    const store = stores.get(storeName);
    if (store && (store.country !== country || store.currency !== currency)) return `Catalog row ${line}: store "${storeName}" mixes countries or currencies.`;
    stores.set(storeName, { country, currency });
    const product = products.get(sku);
    const identity = `${row.name}|${row.description}|${row.brand}`;
    if (product && product !== identity) return `Catalog row ${line}: SKU ${sku} has conflicting product details.`;
    products.set(sku, identity);
    const entry = `${storeName}|${sku}`;
    if (entries.has(entry)) return `Catalog row ${line}: duplicate store and SKU pair ${entry}.`;
    entries.add(entry);
  }
  return null;
}

async function startVisit() {
  const products = selectedProducts();
  if (!customerSelect.value || !products.length) { feedbackElement.textContent = 'Select a customer and at least one available product.'; return; }
  activeCart = await api('shopping', '/api/carts', { method: 'POST', body: JSON.stringify({ customer_id: customerSelect.value, store_id: storeSelect.value, delivery_mode: deliverySelect.value, payment_status: 'pending' }) });
  for (const product of products) await api('shopping', `/api/carts/${activeCart.cart_id}/items`, { method: 'POST', body: JSON.stringify({ product_id: product.product_id, quantity: 1 + Math.floor(Math.random() * 3), unit_price: product.price_amount }) });
  advanceJourney(3);
  feedbackElement.textContent = `Cart ${activeCart.cart_id.slice(0, 8)} created. Choose an outcome.`;
}

async function completeOutcome(outcome) {
  if (!activeCart) { feedbackElement.textContent = 'Start a visit first.'; return; }
  if (outcome === 'abandon') { await api('shopping', `/api/carts/${activeCart.cart_id}`, { method: 'PUT', body: JSON.stringify({ status: 'abandoned' }) }); advanceJourney(3); feedbackElement.textContent = 'Cart abandoned and recorded.'; return; }
  if (outcome === 'cancel_pending' || outcome === 'cancelled') {
    if (!activeOrder) { feedbackElement.textContent = 'Create a successful order before simulating cancellation.'; return; }
    const status = outcome === 'cancel_pending' ? 'pending_cancellation' : 'cancelled';
    activeOrder = await api('shopping', `/api/orders/${activeOrder.order_id}`, { method: 'PUT', body: JSON.stringify({ status }) });
    feedbackElement.textContent = `Order ${status.replaceAll('_', ' ')}.`;
    return;
  }
  const cart = await api('shopping', `/api/carts/${activeCart.cart_id}`);
  const payment = { purchase: { payment_status: 'succeeded', payment_method: 'card', transaction_id: `txn-${crypto.randomUUID()}` }, pending: { payment_status: 'pending', payment_method: 'card' }, failure: { payment_status: 'failed', payment_method: 'card', failure_reason: 'simulated_decline' } }[outcome];
  const order = await api('shopping', '/api/orders', { method: 'POST', body: JSON.stringify({ customer_id: cart.customer_id, store_id: cart.store_id, delivery_mode: cart.delivery_mode, currency: 'USD', items: cart.items.map((item) => ({ product_id: item.product_id, quantity: item.quantity, unit_price: item.unit_price })), ...payment }) });
  activeOrder = order;
  advanceJourney(outcome === 'purchase' ? 5 : 4);
  feedbackElement.textContent = `${order.status.replaceAll('_', ' ')} · ${order.payment_status} · ${order.total_amount} ${order.currency}`;
}

async function simulateBatch() {
  const size = Math.min(100, Math.max(1, Number(document.querySelector('#batch-size').value) || 1));
  if (!loadedCustomers.length || !catalog.length) { feedbackElement.textContent = 'Load customers and a store catalog first.'; return; }
  const outcomes = ['purchase', 'abandon', 'pending', 'failure'];
  for (let index = 0; index < size; index += 1) {
    customerSelect.selectedIndex = Math.floor(Math.random() * loadedCustomers.length);
    [...productSelect.options].forEach((option) => { option.selected = false; });
    const count = 1 + Math.floor(Math.random() * Math.min(10, catalog.length));
    [...productSelect.options].sort(() => Math.random() - 0.5).slice(0, count).forEach((option) => { option.selected = true; });
    await startVisit();
    await completeOutcome(outcomes[Math.floor(Math.random() * outcomes.length)]);
    feedbackElement.textContent = `Simulated ${index + 1} of ${size} journeys.`;
  }
}

function parseCsv(text) {
  const rows = []; let row = []; let field = ''; let quoted = false;
  for (const character of text.replace(/^\uFEFF/, '')) { if (character === '"') quoted = !quoted; else if (character === ',' && !quoted) { row.push(field.trim()); field = ''; } else if (character === '\n' && !quoted) { row.push(field.trim()); rows.push(row); row = []; field = ''; } else if (character !== '\r') field += character; }
  if (field || row.length) { row.push(field.trim()); rows.push(row); }
  const headers = rows.shift();
  return rows.filter((values) => values.some(Boolean)).map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] || ''])));
}

function showCustomerPreview(customers) { pendingCustomers = customers; document.querySelector('#customer-count').textContent = `${customers.length.toLocaleString()} ready`; document.querySelector('#customer-preview-text').textContent = customers.slice(0, 4).map((customer) => `${customer.first_name} ${customer.last_name} · ${customer.email}`).join('\n'); document.querySelector('#import-customers').disabled = customers.length === 0; }
function showCatalogPreview(rows) { pendingCatalog = rows; const validationError = validateCatalogRows(rows); document.querySelector('#catalog-count').textContent = validationError ? 'Invalid CSV' : `${rows.length.toLocaleString()} ready`; document.querySelector('#catalog-preview-text').textContent = validationError || rows.slice(0, 4).map((row) => `${row.store_name} · ${row.sku} · ${row.name} · ${row.currency} ${row.price_amount} · ${row.quantity} units`).join('\n'); document.querySelector('#import-catalog').disabled = rows.length === 0 || Boolean(validationError); document.querySelector('#catalog-feedback').textContent = validationError || 'Product service must be running on port 8002.'; }
async function loadBundledCsv() { const response = await fetch('/data/customers.csv'); showCustomerPreview(parseCsv(await response.text())); document.querySelector('#customer-file-name').textContent = 'customers.csv'; }
async function loadBundledCatalog() { const response = await fetch('/data/catalog.csv'); showCatalogPreview(parseCsv(await response.text())); document.querySelector('#catalog-file-name').textContent = 'catalog.csv'; }
async function importCustomers() { const button = document.querySelector('#import-customers'); button.disabled = true; for (let start = 0; start < pendingCustomers.length; start += 500) await api('crm', '/api/customers/bulk', { method: 'POST', body: JSON.stringify(pendingCustomers.slice(start, start + 500)) }); document.querySelector('#customer-feedback').textContent = `Imported ${pendingCustomers.length.toLocaleString()} customers.`; await loadCustomers(); await loadJourneyData(); }
async function importCatalog() {
  const button = document.querySelector('#import-catalog'); button.disabled = true;
  const validationError = validateCatalogRows(pendingCatalog); if (validationError) throw new Error(validationError);
  const products = await api('product', '/api/products'); const stores = await api('product', '/api/stores');
  const productsBySku = new Map(products.map((product) => [product.sku, product])); const storesByName = new Map(stores.map((store) => [store.name, store]));
  for (const [index, row] of pendingCatalog.entries()) {
    const existingStore = storesByName.get(row.store_name);
    if (existingStore && existingStore.country && existingStore.country !== row.country.trim().toUpperCase()) throw new Error(`Catalog row ${index + 2}: store "${row.store_name}" already belongs to ${existingStore.country}.`);
  }
  for (const [index, row] of pendingCatalog.entries()) {
    let product = productsBySku.get(row.sku);
    if (!product) { product = await api('product', '/api/products', { method: 'POST', body: JSON.stringify({ sku: row.sku, name: row.name, description: row.description || null, brand: row.brand || null, status: row.product_status || 'active' }) }); productsBySku.set(row.sku, product); }
    let store = storesByName.get(row.store_name);
    if (!store) {
      const channel = normalizeStoreChannel(row.channel);
      if (!['physical', 'online', 'both'].includes(channel)) throw new Error(`Catalog row ${index + 2}: channel "${row.channel}" must be physical, online, or both.`);
      store = await api('product', '/api/stores', { method: 'POST', body: JSON.stringify({ name: row.store_name, channel, city: row.city || null, country: row.country || null }) }); storesByName.set(row.store_name, store);
    }
    await api('product', `/api/stores/${store.store_id}/catalog`, { method: 'POST', body: JSON.stringify({ product_id: product.product_id, price_amount: Number(row.price_amount), currency: row.currency || 'USD', status: row.catalog_status || 'active' }) });
    await api('product', `/api/stores/${store.store_id}/inventory`, { method: 'POST', body: JSON.stringify({ product_id: product.product_id, quantity: Number(row.quantity), reserved_quantity: Number(row.reserved_quantity || 0) }) });
  }
  document.querySelector('#catalog-feedback').textContent = `Imported ${pendingCatalog.length.toLocaleString()} catalog rows.`; await loadJourneyData();
}
async function loadCustomers() { const search = encodeURIComponent(document.querySelector('#customer-search').value.trim()); const result = await api('crm', `/api/customers?page=${customerPage}&page_size=100&search=${search}`); loadedCustomers = result.items; customerTotal = result.total; customerTotalPages = result.total_pages; renderJourneyCustomers(); const body = document.querySelector('#customer-table-body'); body.innerHTML = loadedCustomers.map((customer) => `<tr><td><strong>${customer.first_name} ${customer.last_name}</strong></td><td>${customer.email}</td><td>${customer.city || '-'}, ${customer.country || '-'}</td><td>${customer.status}</td><td>${customer.preferred_channel || '-'}</td></tr>`).join('') || '<tr><td colspan="5" class="table-message">No customers match this search.</td></tr>'; document.querySelector('#customer-table-summary').textContent = `${loadedCustomers.length} shown of ${customerTotal} customers`; document.querySelector('#customer-page-label').textContent = `Page ${customerPage} of ${customerTotalPages}`; document.querySelector('#previous-customers').disabled = customerPage <= 1; document.querySelector('#next-customers').disabled = customerPage >= customerTotalPages; }

storeSelect.addEventListener('change', () => loadStoreCatalog().catch((error) => { feedbackElement.textContent = error.message; }));
document.querySelector('#start-journey').addEventListener('click', () => startVisit().catch((error) => { feedbackElement.textContent = error.message; }));
document.querySelectorAll('[data-outcome]').forEach((button) => button.addEventListener('click', () => completeOutcome(button.dataset.outcome).catch((error) => { feedbackElement.textContent = error.message; })));
document.querySelector('#simulate-batch').addEventListener('click', () => simulateBatch().catch((error) => { feedbackElement.textContent = error.message; }));
document.querySelectorAll('[data-tab]').forEach((button) => button.addEventListener('click', () => { document.querySelectorAll('[data-tab]').forEach((tab) => tab.classList.toggle('active', tab === button)); document.querySelectorAll('.view').forEach((view) => { view.hidden = view.id !== `${button.dataset.tab}-view`; }); if (button.dataset.tab === 'customers') loadCustomers().catch(() => {}); if (button.dataset.tab === 'catalog') loadCatalogDirectory().catch((error) => { document.querySelector('#catalog-directory-feedback').textContent = error.message; }); }));
document.querySelector('#load-default-csv').addEventListener('click', () => loadBundledCsv().catch((error) => { document.querySelector('#customer-feedback').textContent = error.message; }));
document.querySelector('#customer-file').addEventListener('change', (event) => { if (event.target.files[0]) event.target.files[0].text().then((text) => showCustomerPreview(parseCsv(text))); });
document.querySelector('#import-customers').addEventListener('click', () => importCustomers().catch((error) => { document.querySelector('#customer-feedback').textContent = error.message; }));
document.querySelector('#load-default-catalog').addEventListener('click', () => loadBundledCatalog().catch((error) => { document.querySelector('#catalog-feedback').textContent = error.message; }));
document.querySelector('#catalog-file').addEventListener('change', (event) => { if (event.target.files[0]) event.target.files[0].text().then((text) => showCatalogPreview(parseCsv(text))); });
document.querySelector('#import-catalog').addEventListener('click', () => importCatalog().catch((error) => { document.querySelector('#catalog-feedback').textContent = error.message; }));
document.querySelector('#refresh-customers').addEventListener('click', () => loadCustomers().catch(() => {}));
document.querySelector('#catalog-store-filter').addEventListener('change', () => loadCatalogDirectory().catch((error) => { document.querySelector('#catalog-directory-feedback').textContent = error.message; }));
document.querySelector('#refresh-catalog').addEventListener('click', () => loadCatalogDirectory().catch((error) => { document.querySelector('#catalog-directory-feedback').textContent = error.message; }));
document.querySelector('#previous-customers').addEventListener('click', () => { if (customerPage > 1) { customerPage -= 1; loadCustomers(); } });
document.querySelector('#next-customers').addEventListener('click', () => { if (customerPage < customerTotalPages) { customerPage += 1; loadCustomers(); } });
document.querySelector('#customer-search').addEventListener('input', () => { customerPage = 1; window.clearTimeout(window.customerSearchTimer); window.customerSearchTimer = window.setTimeout(() => loadCustomers(), 250); });
renderSteps();
loadJourneyData();
