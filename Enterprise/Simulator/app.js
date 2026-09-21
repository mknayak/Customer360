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
let pendingCampaigns = [];
let customerPage = 1;
let customerTotalPages = 1;
let customerTotal = 0;
let campaigns = [];
let channels = [];
let feedbackRecords = [];
let carts = [];
let orders = [];
let cartTotal = 0;
let orderTotal = 0;
let productsById = new Map();
let catalogDirectoryRows = [];
let currentCustomerId = '';
let sites = [];
let visits = [];
let events = [];
let activeSite = null;
let activeVisit = null;
let workflowCorrelationId = null;

const api = async (service, path, options = {}) => {
  const response = await fetch(`/${service}${path}`, { headers: { 'Content-Type': 'application/json' }, ...options });
  if (!response.ok) throw new Error(`${service} rejected request: ${response.status}`);
  return response.status === 204 ? null : response.json();
};

async function recordEvent(sourceService, eventType, aggregateType, aggregateId, payload, correlationId = workflowCorrelationId || crypto.randomUUID()) {
  return api('events', '/api/events', {
    method: 'POST',
    body: JSON.stringify({ source_service: sourceService, event_type: eventType, aggregate_type: aggregateType, aggregate_id: aggregateId, payload, correlation_id: correlationId }),
  });
}

const contentPages = {
  about: 'About Northstar',
  products: 'Products',
  news: 'News',
  blog: 'Blog',
  stories: 'Customer stories',
  sustainability: 'Sustainability',
  'company-information': 'Company information',
};

function renderUserVisitCustomers() {
  const select = document.querySelector('#user-visit-customer');
  if (!select) return;
  select.innerHTML = '<option value="">Anonymous visitor</option>' + loadedCustomers.map((customer) => `<option value="${customer.customer_id}">${customer.first_name} ${customer.last_name} · ${customer.email}</option>`).join('');
  if (currentCustomerId) select.value = currentCustomerId;
}

function selectedUserVisitPages() {
  return [...document.querySelector('#user-visit-page-selection').selectedOptions].map((option) => option.value).filter((page) => contentPages[page]);
}

function randomBetween(minimum, maximum) {
  return minimum + Math.floor(Math.random() * (maximum - minimum + 1));
}

function chooseUserVisitFlow(selectedFlow) {
  if (selectedFlow !== 'random') return selectedFlow;
  return randomItem(['anonymous_browse', 'anonymous_login_browse', 'product_cart_abandon', 'checkout_success', 'checkout_failed']);
}

function knownUserForVisit(selectedCustomerId) {
  if (selectedCustomerId) return selectedCustomerId;
  return loadedCustomers.length ? randomItem(loadedCustomers).customer_id : null;
}

async function simulateCommerceStep(flow, sessionId, customerId, summary) {
  const product = catalog[0];
  if (!customerId || !product || !activeSite) return;
  await recordEvent('content-site', 'ProductViewed', 'product', product.product_id, { customer_id: customerId, session_id: sessionId, product_id: product.product_id, title: product.name }, sessionId);
  summary.productViews += 1;
  const cart = await api('shopping', '/api/carts', { method: 'POST', body: JSON.stringify({ customer_id: customerId, site_id: activeSite.site_id, store_id: storeSelect.value, delivery_mode: deliverySelect.value }) });
  await api('shopping', `/api/carts/${cart.cart_id}/items`, { method: 'POST', body: JSON.stringify({ product_id: product.product_id, quantity: 1, unit_price: product.price_amount }) });
  summary.carts += 1;
  await recordEvent('content-site', 'CartCreated', 'cart', cart.cart_id, { customer_id: customerId, session_id: sessionId, product_id: product.product_id }, sessionId);
  if (flow === 'product_cart_abandon') {
    await api('shopping', `/api/carts/${cart.cart_id}`, { method: 'PUT', body: JSON.stringify({ status: 'abandoned' }) });
    summary.abandoned += 1;
    return;
  }
  await recordEvent('content-site', 'CheckoutStarted', 'cart', cart.cart_id, { customer_id: customerId, session_id: sessionId, cart_id: cart.cart_id }, sessionId);
  summary.checkouts += 1;
  const payment = flow === 'checkout_failed'
    ? { payment_status: 'failed', payment_method: 'card', failure_reason: 'simulated_decline' }
    : { payment_status: 'succeeded', payment_method: 'card', transaction_id: `txn-${crypto.randomUUID()}` };
  const order = await api('shopping', '/api/orders', { method: 'POST', body: JSON.stringify({ customer_id: customerId, site_id: activeSite.site_id, store_id: storeSelect.value, delivery_mode: deliverySelect.value, currency: product.currency || 'USD', items: [{ product_id: product.product_id, quantity: 1, unit_price: product.price_amount }], ...payment }) });
  await recordEvent('content-site', flow === 'checkout_failed' ? 'PaymentFailed' : 'OrderCreated', 'order', order.order_id, { customer_id: customerId, session_id: sessionId, order_id: order.order_id, payment_status: order.payment_status }, sessionId);
  if (flow === 'checkout_failed') summary.paymentFailures += 1;
  else summary.orders += 1;
}

async function simulateUserVisits() {
  const button = document.querySelector('#simulate-user-visits');
  const feedback = document.querySelector('#user-visits-feedback');
  const selectedFlow = document.querySelector('#user-visit-flow').value;
  const selectedPages = selectedUserVisitPages();
  const count = Math.min(250, Math.max(1, Number(document.querySelector('#user-visit-count').value) || 1));
  const pagesPerSession = Math.min(selectedPages.length, Math.max(1, Number(document.querySelector('#user-visit-pages').value) || 1));
  const dwellSeconds = Math.min(300, Math.max(1, Number(document.querySelector('#user-visit-dwell').value) || 1));
  const searchRate = Math.min(100, Math.max(0, Number(document.querySelector('#user-visit-search-rate').value) || 0));
  const contentRate = Math.min(100, Math.max(0, Number(document.querySelector('#user-visit-content-rate').value) || 0));
  const customerId = document.querySelector('#user-visit-customer').value || null;
  if (!selectedPages.length) throw new Error('Select at least one page.');
  const summary = { pageVisits: 0, contentViews: 0, searches: 0, timeOnPage: 0, exits: 0, logins: 0, productViews: 0, carts: 0, abandoned: 0, checkouts: 0, orders: 0, paymentFailures: 0 };
  button.disabled = true;
  document.querySelector('#user-visits-state').textContent = 'Running';
  feedback.textContent = `Starting ${count} user visits across ${selectedPages.length} selected pages...`;
  try {
    for (let index = 0; index < count; index += 1) {
      const sessionId = crypto.randomUUID();
      const flow = chooseUserVisitFlow(selectedFlow);
      const loginFlow = flow !== 'anonymous_browse';
      const knownCustomerId = loginFlow ? knownUserForVisit(customerId) : null;
      const pages = [...selectedPages].sort(() => Math.random() - 0.5).slice(0, pagesPerSession);
      await recordEvent('content-site', 'PageVisit', 'content_session', sessionId, { customer_id: null, session_id: sessionId, flow, path: '/content.html' }, sessionId);
      summary.pageVisits += 1;
      if (loginFlow && knownCustomerId) {
        await recordEvent('content-site', 'UserLogin', 'user_session', sessionId, { customer_id: knownCustomerId, session_id: sessionId, method: 'simulated_login' }, sessionId);
        summary.logins += 1;
      }
      for (const page of pages) {
        const pageId = `${sessionId}:${page}`;
        if (Math.random() * 100 < contentRate) {
          await recordEvent('content-site', 'ContentView', 'content_page', pageId, { customer_id: knownCustomerId, session_id: sessionId, content_id: page, title: contentPages[page], path: `/content.html#${page}` }, sessionId);
          summary.contentViews += 1;
        }
        if (Math.random() * 100 < searchRate) {
          await recordEvent('content-site', 'Search', 'content_session', sessionId, { customer_id: knownCustomerId, session_id: sessionId, query: contentPages[page].toLowerCase(), path: '/content.html' }, sessionId);
          summary.searches += 1;
        }
        await recordEvent('content-site', 'TimeOnPage', 'content_page', pageId, { customer_id: knownCustomerId, session_id: sessionId, content_id: page, duration_seconds: randomBetween(Math.max(1, Math.floor(dwellSeconds / 2)), dwellSeconds) }, sessionId);
        summary.timeOnPage += 1;
      }
      if (['product_cart_abandon', 'checkout_success', 'checkout_failed'].includes(flow)) await simulateCommerceStep(flow, sessionId, knownCustomerId, summary);
      await recordEvent('content-site', 'Exit', 'content_session', sessionId, { customer_id: knownCustomerId, session_id: sessionId, flow, last_page: pages[pages.length - 1], page_count: pages.length }, sessionId);
      summary.exits += 1;
      feedback.textContent = `Simulated ${index + 1} of ${count} user visits...`;
    }
    document.querySelector('#user-visits-state').textContent = `${count} sessions`;
    feedback.textContent = `Created ${count} sessions · ${summary.logins} logins · ${summary.productViews} products · ${summary.carts} carts · ${summary.abandoned} abandoned · ${summary.checkouts} checkouts · ${summary.orders} orders · ${summary.paymentFailures} payment failures.`;
  } finally {
    button.disabled = false;
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

function selectedProducts() {
  return [...productSelect.selectedOptions].map((option) => catalog.find((item) => item.product_id === option.value)).filter(Boolean);
}

function renderJourneyCustomers() {
  customerSelect.innerHTML = loadedCustomers.map((customer) => `<option value="${customer.customer_id}">${customer.first_name} ${customer.last_name} · ${customer.email}</option>`).join('') || '<option value="">Load customers first</option>';
  if (currentCustomerId && loadedCustomers.some((customer) => customer.customer_id === currentCustomerId)) customerSelect.value = currentCustomerId;
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

async function ensureSite() {
  const sites = await api('site', '/api/sites');
  const siteName = 'Northstar Shopping Simulator';
  let site = sites.find((item) => item.name === siteName);
  if (!site) {
    site = await api('site', '/api/sites', {
      method: 'POST',
      body: JSON.stringify({
        name: siteName,
        type: 'WEBSITE',
        city: 'Remote',
        country: 'US',
        status: 'active',
      }),
    });
    await recordEvent('site', 'SiteCreated', 'site', site.site_id, { name: site.name, type: site.type });
  }
  activeSite = site;
  return site;
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
    renderUserVisitCustomers();
    const store = await seedCatalog();
    const stores = await api('product', '/api/stores');
    storeSelect.innerHTML = stores.map((item) => `<option value="${item.store_id}">${item.name} · ${item.city || item.channel}</option>`).join('');
    storeSelect.value = store.store_id;
    if (!currentCustomerId && loadedCustomers[0]) currentCustomerId = loadedCustomers[0].customer_id;
    renderJourneyCustomers();
    await ensureSite();
    await loadStoreCatalog();
    activateLeftSidebar(document.querySelector('.tab.active')?.dataset.tab || 'journey');
    apiStatusElement.textContent = 'CRM · Product · Shopping · Site connected';
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
  catalogDirectoryRows = rows;
  document.querySelector('#catalog-directory-count').textContent = `${rows.length.toLocaleString()} products`;
  document.querySelector('#catalog-table-body').innerHTML = rows.map((row) => `<tr class="clickable-row" data-record-type="catalog" data-record-id="${row.catalog_entry_id}"><td><strong>${row.product.name || 'Unknown product'}</strong></td><td>${row.product.sku || '-'}</td><td>${row.store.name}</td><td>${row.currency} ${Number(row.price_amount).toFixed(2)}</td><td>${row.available}</td><td>${row.status}</td></tr>`).join('') || '<tr><td colspan="6" class="table-message">No catalog entries found.</td></tr>';
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
  const site = await ensureSite();
  const workflow = await api('orchestration', '/api/workflows/shopping-journey', {
    method: 'POST',
    body: JSON.stringify({
      customer_id: customerSelect.value,
      site_id: site.site_id,
      store_id: storeSelect.value,
      delivery_mode: deliverySelect.value,
      items: products.map((product) => ({ product_id: product.product_id, quantity: 1 + Math.floor(Math.random() * 3), unit_price: product.price_amount })),
    }),
  });
  workflowCorrelationId = workflow.correlation_id;
  activeVisit = { visit_id: workflow.visit_id, site_id: site.site_id, customer_id: customerSelect.value, channel: 'web' };
  activeCart = { cart_id: workflow.cart_id, customer_id: customerSelect.value, store_id: storeSelect.value, delivery_mode: deliverySelect.value };
  advanceJourney(3);
  feedbackElement.textContent = `Workflow ${workflow.correlation_id.slice(0, 8)} created visit ${activeVisit.visit_id.slice(0, 8)} and cart ${activeCart.cart_id.slice(0, 8)}. Choose an outcome.`;
}

async function completeOutcome(outcome) {
  if (!activeCart) { feedbackElement.textContent = 'Start a visit first.'; return; }
  if (outcome === 'abandon') { await api('shopping', `/api/carts/${activeCart.cart_id}`, { method: 'PUT', body: JSON.stringify({ status: 'abandoned' }) }); await recordEvent('shopping', 'CartAbandoned', 'cart', activeCart.cart_id, { customer_id: activeCart.customer_id }); advanceJourney(3); feedbackElement.textContent = 'Cart abandoned and recorded.'; return; }
  if (outcome === 'cancel_pending' || outcome === 'cancelled') {
    if (!activeOrder) { feedbackElement.textContent = 'Create a successful order before simulating cancellation.'; return; }
    const status = outcome === 'cancel_pending' ? 'pending_cancellation' : 'cancelled';
    activeOrder = await api('shopping', `/api/orders/${activeOrder.order_id}`, { method: 'PUT', body: JSON.stringify({ status }) });
    await recordEvent('shopping', 'OrderStatusChanged', 'order', activeOrder.order_id, { customer_id: activeOrder.customer_id, status });
    feedbackElement.textContent = `Order ${status.replaceAll('_', ' ')}.`;
    return;
  }
  const cart = await api('shopping', `/api/carts/${activeCart.cart_id}`);
  const payment = { purchase: { payment_status: 'succeeded', payment_method: 'card', transaction_id: `txn-${crypto.randomUUID()}` }, pending: { payment_status: 'pending', payment_method: 'card' }, failure: { payment_status: 'failed', payment_method: 'card', failure_reason: 'simulated_decline' } }[outcome];
  const order = await api('shopping', '/api/orders', { method: 'POST', body: JSON.stringify({ customer_id: cart.customer_id, store_id: cart.store_id, delivery_mode: cart.delivery_mode, currency: 'USD', items: cart.items.map((item) => ({ product_id: item.product_id, quantity: item.quantity, unit_price: item.unit_price })), ...payment }) });
  activeOrder = order;
  await recordEvent('shopping', 'OrderCreated', 'order', order.order_id, { customer_id: order.customer_id, cart_id: activeCart.cart_id, status: order.status, payment_status: order.payment_status });
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
function validateCampaignRows(rows) {
  const statuses = ['draft', 'scheduled', 'active', 'paused', 'ended', 'cancelled'];
  const channelTypes = ['email', 'sms', 'push', 'paid_search', 'social', 'direct_mail', 'in_store', 'web'];
  for (const [index, row] of rows.entries()) {
    const line = index + 2;
    if (!row.campaign_name?.trim()) return `Campaign row ${line}: campaign_name is required.`;
    if (!row.audience_name?.trim()) return `Campaign row ${line}: audience_name is required.`;
    if (!row.channel_name?.trim()) return `Campaign row ${line}: channel_name is required.`;
    if (!channelTypes.includes((row.channel_type || '').trim())) return `Campaign row ${line}: channel_type must be one of ${channelTypes.join(', ')}.`;
    if (row.status && !statuses.includes(row.status.trim())) return `Campaign row ${line}: status must be one of ${statuses.join(', ')}.`;
    const allocation = Number(row.allocation_percent || 0);
    if (Number.isNaN(allocation) || allocation < 0 || allocation > 100) return `Campaign row ${line}: allocation_percent must be between 0 and 100.`;
    const startDate = row.start_date ? Date.parse(row.start_date) : null;
    const endDate = row.end_date ? Date.parse(row.end_date) : null;
    if (row.start_date && Number.isNaN(startDate)) return `Campaign row ${line}: start_date is not a valid date.`;
    if (row.end_date && Number.isNaN(endDate)) return `Campaign row ${line}: end_date is not a valid date.`;
    if (startDate && endDate && endDate < startDate) return `Campaign row ${line}: end_date cannot be before start_date.`;
  }
  return null;
}
function showCampaignPreview(rows) { pendingCampaigns = rows; const validationError = validateCampaignRows(rows); document.querySelector('#campaign-count').textContent = validationError ? 'Invalid CSV' : `${rows.length.toLocaleString()} ready`; document.querySelector('#campaign-preview-text').textContent = validationError || rows.slice(0, 4).map((row) => `${row.campaign_name} · ${row.audience_name} · ${row.channel_name} · ${row.allocation_percent || 0}%`).join('\n'); document.querySelector('#import-campaigns').disabled = rows.length === 0 || Boolean(validationError); document.querySelector('#campaign-feedback').textContent = validationError || 'Marketing service must be running on port 8006.'; }
async function loadBundledCsv() { const response = await fetch('/data/customers.csv'); showCustomerPreview(parseCsv(await response.text())); document.querySelector('#customer-file-name').textContent = 'customers.csv'; }
async function loadBundledCatalog() { const response = await fetch('/data/catalog.csv'); showCatalogPreview(parseCsv(await response.text())); document.querySelector('#catalog-file-name').textContent = 'catalog.csv'; }
async function loadBundledCampaigns() { const response = await fetch('/data/campaigns.csv'); showCampaignPreview(parseCsv(await response.text())); document.querySelector('#campaign-file-name').textContent = 'campaigns.csv'; }
async function importCustomers() { const button = document.querySelector('#import-customers'); button.disabled = true; for (let start = 0; start < pendingCustomers.length; start += 500) await api('crm', '/api/customers/bulk', { method: 'POST', body: JSON.stringify(pendingCustomers.slice(start, start + 500)) }); await recordEvent('crm', 'CustomersImported', 'customer_batch', crypto.randomUUID(), { count: pendingCustomers.length }); document.querySelector('#customer-feedback').textContent = `Imported ${pendingCustomers.length.toLocaleString()} customers.`; await loadCustomers(); await loadJourneyData(); }
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
  await recordEvent('product', 'CatalogImported', 'catalog_batch', crypto.randomUUID(), { rows: pendingCatalog.length, products: productsBySku.size, stores: storesByName.size }); document.querySelector('#catalog-feedback').textContent = `Imported ${pendingCatalog.length.toLocaleString()} catalog rows.`; await loadJourneyData();
  await recordEvent('marketing', 'CampaignsImported', 'campaign_batch', crypto.randomUUID(), { rows: pendingCampaigns.length });
  await recordEvent('marketing', 'CampaignInteractionRecorded', 'campaign_interaction', interaction.interaction_id, { customer_id: customerId, campaign_id: campaignId, event_type: eventType });
  await recordEvent('feedback', 'FeedbackSubmitted', 'feedback', record.feedback_id, { customer_id: record.customer_id, campaign_id: record.campaign_id, rating: record.rating, sentiment: record.sentiment });
}
async function loadCustomers() { const search = encodeURIComponent(document.querySelector('#customer-search').value.trim()); const result = await api('crm', `/api/customers?page=${customerPage}&page_size=100&search=${search}`); loadedCustomers = result.items; customerTotal = result.total; customerTotalPages = result.total_pages; renderJourneyCustomers(); const body = document.querySelector('#customer-table-body'); body.innerHTML = loadedCustomers.map((customer) => `<tr class="clickable-row" data-record-type="customer" data-record-id="${customer.customer_id}"><td><strong>${customer.first_name} ${customer.last_name}</strong></td><td>${customer.email}</td><td>${customer.city || '-'}, ${customer.country || '-'}</td><td>${customer.status}</td><td>${customer.preferred_channel || '-'}</td></tr>`).join('') || '<tr><td colspan="5" class="table-message">No customers match this search.</td></tr>'; document.querySelector('#customer-table-summary').textContent = `${loadedCustomers.length} shown of ${customerTotal} customers`; document.querySelector('#customer-page-label').textContent = `Page ${customerPage} of ${customerTotalPages}`; document.querySelector('#previous-customers').disabled = customerPage <= 1; document.querySelector('#next-customers').disabled = customerPage >= customerTotalPages; }
function formatDateTime(value) {
  return value ? new Date(value).toLocaleString() : '-';
}
function dateQueryValue(value, endOfDay = false) {
  if (!value) return '';
  return `${value}T${endOfDay ? '23:59:59' : '00:00:00'}`;
}
function orderFilterQuery() {
  const params = new URLSearchParams();
  params.set('page', '1');
  params.set('page_size', '20');
  const customerId = document.querySelector('#orders-customer-filter').value;
  const startDate = dateQueryValue(document.querySelector('#orders-start-date').value);
  const endDate = dateQueryValue(document.querySelector('#orders-end-date').value, true);
  if (customerId) params.set('customer_id', customerId);
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  return params.toString() ? `?${params}` : '';
}
function renderOrderCustomerFilter() {
  const selectedCustomer = document.querySelector('#orders-customer-filter').value || currentCustomerId;
  document.querySelector('#orders-customer-filter').innerHTML = '<option value="">All customers</option>' + loadedCustomers.map((customer) => `<option value="${customer.customer_id}">${customer.first_name} ${customer.last_name} · ${customer.email}</option>`).join('');
  document.querySelector('#orders-customer-filter').value = loadedCustomers.some((customer) => customer.customer_id === selectedCustomer) ? selectedCustomer : '';
}
let leftSidebarGroups = null;
const movedSidebarNodes = [];
function initializeLeftSidebarGroups() {
  leftSidebarGroups = {
    journey: { kicker: 'Journey widget', title: 'Session context', widget: renderJourneySidebar },
    orders: { kicker: 'Commerce widget', title: 'Shopping stats', widget: renderOrdersSidebar },
    customers: { kicker: 'CRM import', title: 'Load customers', nodes: [document.querySelector('#customers-view > .customer-heading'), document.querySelector('#customers-view > .customer-actions'), document.querySelector('#customers-view > .customer-preview'), document.querySelector('#import-customers'), document.querySelector('#customer-feedback')] },
    catalog: { kicker: 'Product import', title: 'Load catalog', nodes: [document.querySelector('#catalog-view .customer-import')] },
    sites: { kicker: 'Site view', title: 'Session stats', widget: renderSitesSidebar },
    engagement: { kicker: 'Marketing import', title: 'Load campaigns', nodes: [document.querySelector('#engagement-view > .customer-import')] },
    'user-visits': { kicker: 'Content simulation', title: 'User visits', widget: () => `<div class="stat-grid"><div class="stat-card"><span>Available pages</span><strong>${Object.keys(contentPages).length}</strong></div><div class="stat-card"><span>Event source</span><strong>content-site</strong></div></div><p class="table-summary">Use the main panel to generate correlated content sessions.</p>` },
    events: { kicker: 'Event backbone', title: 'Stream stats', widget: renderEventsSidebar },
  };
}
function restoreLeftSidebarNodes() {
  while (movedSidebarNodes.length) {
    const { node, placeholder } = movedSidebarNodes.pop();
    placeholder.replaceWith(node);
  }
}
function activateLeftSidebar(tab) {
  if (!leftSidebarGroups) initializeLeftSidebarGroups();
  restoreLeftSidebarNodes();
  const group = leftSidebarGroups[tab];
  document.querySelector('#left-sidebar-kicker').textContent = group?.kicker || 'Simulator';
  document.querySelector('#left-sidebar-title').textContent = group?.title || 'Actions';
  document.querySelector('#left-sidebar-body').innerHTML = '';
  if (group?.widget) {
    document.querySelector('#left-sidebar-body').innerHTML = group.widget();
    wireSidebarControls();
    return;
  }
  for (const node of group?.nodes || []) {
    if (!node || !node.parentNode) continue;
    const placeholder = document.createComment('left-sidebar-placeholder');
    node.parentNode.insertBefore(placeholder, node);
    movedSidebarNodes.push({ node, placeholder });
    document.querySelector('#left-sidebar-body').appendChild(node);
  }
}
function currentCustomerOptions() {
  return '<option value="">No current customer</option>' + loadedCustomers.map((customer) => `<option value="${customer.customer_id}" ${customer.customer_id === currentCustomerId ? 'selected' : ''}>${customer.first_name} ${customer.last_name} · ${customer.email}</option>`).join('');
}
function currentCustomerCard() {
  const customer = loadedCustomers.find((item) => item.customer_id === currentCustomerId);
  const label = customer ? `${customer.first_name} ${customer.last_name}<br><span class="muted-cell">${customer.email}</span>` : 'No customer selected';
  return `<label class="control">Current customer<select id="current-customer-select">${currentCustomerOptions()}</select></label><div class="stat-card"><span>Selected</span><strong>${label}</strong></div>`;
}
function renderJourneySidebar() {
  const selectedCount = productSelect ? productSelect.selectedOptions.length : 0;
  return `${currentCustomerCard()}<div class="stat-grid"><div class="stat-card"><span>Journey state</span><strong>${stateElement.textContent}</strong></div><div class="stat-card"><span>Catalog options</span><strong>${catalog.length}</strong></div><div class="stat-card"><span>Selected products</span><strong>${selectedCount}</strong></div><div class="stat-card"><span>Active cart</span><strong>${activeCart ? activeCart.cart_id.slice(0, 8) : '-'}</strong></div></div>`;
}
function renderOrdersSidebar() {
  const paid = orders.filter((order) => order.payment_status === 'succeeded').length;
  const failed = orders.filter((order) => order.payment_status === 'failed').length;
  return `${currentCustomerCard()}<div class="stat-grid"><div class="stat-card"><span>Total carts</span><strong>${cartTotal}</strong></div><div class="stat-card"><span>Total orders</span><strong>${orderTotal}</strong></div><div class="stat-card"><span>Paid on page</span><strong>${paid}</strong></div><div class="stat-card"><span>Failed on page</span><strong>${failed}</strong></div></div><p class="table-summary">The main table always shows page 1 with 20 carts and 20 orders.</p>`;
}
function renderSitesSidebar() {
  const visitCount = visits.length;
  const siteCount = sites.length;
  return `${currentCustomerCard()}<div class="stat-grid"><div class="stat-card"><span>Sites</span><strong>${siteCount}</strong></div><div class="stat-card"><span>Visits</span><strong>${visitCount}</strong></div><div class="stat-card"><span>Likely links</span><strong>customer_id + site_id</strong></div><div class="stat-card"><span>Source</span><strong>site service</strong></div></div><p class="table-summary">Customer and order records connect by IDs; the site service owns visits and the site metadata.</p>`;
}
function renderEventsSidebar() {
  const sourceCount = new Set(events.map((event) => event.source_service)).size;
  const typeCount = new Set(events.map((event) => event.event_type)).size;
  const correlationCount = new Set(events.map((event) => event.correlation_id).filter(Boolean)).size;
  const filter = document.querySelector('#events-correlation-filter')?.value || 'All workflows';
  return `<div class="stat-grid"><div class="stat-card"><span>Events loaded</span><strong>${events.length}</strong></div><div class="stat-card"><span>Sources</span><strong>${sourceCount}</strong></div><div class="stat-card"><span>Event types</span><strong>${typeCount}</strong></div><div class="stat-card"><span>Correlations</span><strong>${correlationCount}</strong></div></div><p class="table-summary">Filter: ${filter}</p><p class="table-summary">Events are immutable records linked by correlation ID.</p>`;
}
function syncCurrentCustomer(customerId) {
  currentCustomerId = customerId || '';
  if (currentCustomerId && loadedCustomers.some((customer) => customer.customer_id === currentCustomerId)) {
    customerSelect.value = currentCustomerId;
    document.querySelector('#engagement-customer').value = currentCustomerId;
  }
  if (document.querySelector('#orders-customer-filter')) document.querySelector('#orders-customer-filter').value = currentCustomerId;
  activateLeftSidebar(document.querySelector('.tab.active')?.dataset.tab || 'journey');
}
function wireSidebarControls() {
  const currentCustomerSelect = document.querySelector('#current-customer-select');
  if (currentCustomerSelect) currentCustomerSelect.addEventListener('change', () => { syncCurrentCustomer(currentCustomerSelect.value); if (document.querySelector('.tab.active')?.dataset.tab === 'orders') loadCartOrderData().catch((error) => { document.querySelector('#orders-feedback').textContent = error.message; }); });
}
function renderCartOrderData() {
  const customerLabels = new Map(loadedCustomers.map((customer) => [customer.customer_id, `${customer.first_name} ${customer.last_name}<br><span class="muted-cell">${customer.email}</span>`]));
  document.querySelector('#cart-table-body').innerHTML = carts.map((cart) => `<tr class="clickable-row" data-record-type="cart" data-record-id="${cart.cart_id}"><td><strong>${cart.cart_id.slice(0, 8)}</strong></td><td>${customerLabels.get(cart.customer_id) || cart.customer_id}</td><td>${cart.status}</td><td>${cart.payment_status}</td><td>${cart.delivery_mode}</td><td>${cart.items.length}</td><td>${formatDateTime(cart.created_at)}</td></tr>`).join('') || '<tr><td colspan="7" class="table-message">No carts match these filters.</td></tr>';
  document.querySelector('#order-table-body').innerHTML = orders.map((order) => `<tr class="clickable-row" data-record-type="order" data-record-id="${order.order_id}"><td><strong>${order.order_id.slice(0, 8)}</strong></td><td>${customerLabels.get(order.customer_id) || order.customer_id}</td><td>${order.status}</td><td>${order.payment_status}</td><td>${order.currency} ${Number(order.total_amount).toFixed(2)}</td><td>${order.fulfillment_status}</td><td>${formatDateTime(order.created_at)}</td></tr>`).join('') || '<tr><td colspan="7" class="table-message">No orders match these filters.</td></tr>';
  document.querySelector('#orders-state').textContent = `${cartTotal} carts · ${orderTotal} orders`;
  document.querySelector('#orders-page-summary').textContent = `Showing page 1 · ${carts.length} of ${cartTotal} carts · ${orders.length} of ${orderTotal} orders`;
}
async function loadCartOrderData() {
  const result = await api('crm', '/api/customers?page=1&page_size=100'); loadedCustomers = result.items; renderJourneyCustomers(); renderOrderCustomerFilter();
  const query = orderFilterQuery();
  const [cartPage, orderPage, products] = await Promise.all([api('shopping', `/api/carts${query}`), api('shopping', `/api/orders${query}`), api('product', '/api/products')]);
  carts = cartPage.items; orders = orderPage.items; cartTotal = cartPage.total; orderTotal = orderPage.total;
  productsById = new Map(products.map((product) => [product.product_id, product]));
  renderCartOrderData();
  if (document.querySelector('.tab.active')?.dataset.tab === 'orders') activateLeftSidebar('orders');
  document.querySelector('#orders-feedback').textContent = 'Shopping records loaded.';
}
function customerDetailLabel(customerId) {
  const customer = loadedCustomers.find((item) => item.customer_id === customerId);
  return customer ? `${customer.first_name} ${customer.last_name}<br><span class="muted-cell">${customer.email}</span>` : customerId;
}
function productDetailLabel(productId) {
  const product = productsById.get(productId);
  return product ? `${product.name}<br><span class="muted-cell">${product.sku || product.product_id.slice(0, 8)}</span>` : productId;
}
function detailList(fields) {
  return `<dl class="detail-list">${fields.map(([label, value]) => `<dt>${label}</dt><dd>${value ?? '-'}</dd>`).join('')}</dl>`;
}
function openDetail(type, title, summary, fields, table = '') {
  document.querySelector('#record-detail-type').textContent = type;
  document.querySelector('#record-detail-title').textContent = title;
  document.querySelector('#record-detail-body').innerHTML = `<p class="detail-summary">${summary}</p>${detailList(fields)}${table}`;
  document.querySelector('#record-detail-panel').hidden = false;
}
function itemTable(items, type) {
  return `<div class="table-wrap"><table><thead><tr><th>Product</th><th>Qty</th><th>Unit</th>${type === 'order' ? '<th>Disc.</th>' : ''}</tr></thead><tbody>${items.map((item) => `<tr><td>${productDetailLabel(item.product_id)}</td><td>${item.quantity}</td><td>${Number(item.unit_price).toFixed(2)}</td>${type === 'order' ? `<td>${Number(item.discount_amount || 0).toFixed(2)}</td>` : ''}</tr>`).join('') || `<tr><td colspan="${type === 'order' ? 4 : 3}" class="table-message">No items found.</td></tr>`}</tbody></table></div>`;
}
function showCartOrderDetail(type, id) {
  const record = type === 'cart' ? carts.find((item) => item.cart_id === id) : orders.find((item) => item.order_id === id);
  if (!record) return;
  const items = record.items || [];
  const summary = type === 'cart' ? `${record.status} · ${record.payment_status} · ${items.length} items` : `${record.status} · ${record.payment_status} · ${record.currency} ${Number(record.total_amount).toFixed(2)}`;
  openDetail(type === 'cart' ? 'Cart details' : 'Order details', type === 'cart' ? `Cart ${record.cart_id.slice(0, 8)}` : `Order ${record.order_id.slice(0, 8)}`, summary, [['Customer', customerDetailLabel(record.customer_id)], ['Created', formatDateTime(record.created_at)], ['Delivery', record.delivery_mode || '-'], ['Fulfilment', record.fulfillment_status || '-']], itemTable(items, type));
}
function showSiteDetail(id) {
  const site = sites.find((item) => item.site_id === id);
  if (!site) return;
  const siteVisits = visits.filter((visit) => visit.site_id === site.site_id);
  openDetail('Site details', site.name, `${site.type} · ${site.status}`, [['Site ID', site.site_id], ['City', site.city || '-'], ['Country', site.country || '-'], ['Opened', formatDateTime(site.opened_date)], ['Visit count', String(siteVisits.length)]], siteVisits.length ? `<div class="table-wrap"><table><thead><tr><th>Customer</th><th>Channel</th><th>Started</th><th>Ended</th></tr></thead><tbody>${siteVisits.map((visit) => `<tr><td>${customerDetailLabel(visit.customer_id)}</td><td>${visit.channel}</td><td>${formatDateTime(visit.started_at)}</td><td>${formatDateTime(visit.ended_at)}</td></tr>`).join('')}</tbody></table></div>` : '');
}
function showVisitDetail(id) {
  const visit = visits.find((item) => item.visit_id === id);
  if (!visit) return;
  const site = sites.find((item) => item.site_id === visit.site_id);
  openDetail('Visit details', `Visit ${visit.visit_id.slice(0, 8)}`, `${visit.channel} session`, [['Customer', customerDetailLabel(visit.customer_id)], ['Site', site ? site.name : visit.site_id], ['Started', formatDateTime(visit.started_at)], ['Ended', formatDateTime(visit.ended_at)], ['Site type', site ? site.type : '-']]);
}
function showCustomerDetail(id) {
  const customer = loadedCustomers.find((item) => item.customer_id === id);
  if (!customer) return;
  openDetail('Customer details', `${customer.first_name} ${customer.last_name}`, customer.email, [['Customer ID', customer.customer_id], ['Status', customer.status], ['Location', `${customer.city || '-'}, ${customer.country || '-'}`], ['Age group', customer.age_group || '-'], ['Channel', customer.preferred_channel || '-']]);
}
function showCatalogDetail(id) {
  const row = catalogDirectoryRows.find((item) => item.catalog_entry_id === id);
  if (!row) return;
  openDetail('Catalog details', row.product.name || 'Unknown product', `${row.currency} ${Number(row.price_amount).toFixed(2)} · ${row.available} available`, [['SKU', row.product.sku || '-'], ['Brand', row.product.brand || '-'], ['Store', row.store.name], ['Channel', row.store.channel], ['Status', row.status]]);
}
function showCampaignDetail(id) {
  const campaign = campaigns.find((item) => item.campaign_id === id);
  if (!campaign) return;
  openDetail('Campaign details', campaign.name, campaign.objective || 'No objective set', [['Status', campaign.status], ['Budget', campaign.budget_amount == null ? '-' : `${campaign.currency} ${Number(campaign.budget_amount).toLocaleString()}`], ['Starts', formatDateTime(campaign.start_date)], ['Ends', formatDateTime(campaign.end_date)], ['Campaign ID', campaign.campaign_id]]);
}
function showFeedbackDetail(id) {
  const record = feedbackRecords.find((item) => item.feedback_id === id);
  if (!record) return;
  const campaign = campaigns.find((item) => item.campaign_id === record.campaign_id);
  openDetail('Feedback details', `${record.sentiment} · rating ${record.rating}`, record.comment || 'No comment', [['Customer', customerDetailLabel(record.customer_id)], ['Campaign', campaign?.name || record.campaign_id || '-'], ['Source', record.source], ['Status', record.status], ['Submitted', formatDateTime(record.submitted_at)]]);
}
function showTableDetail(type, id) {
  if (type === 'cart' || type === 'order') showCartOrderDetail(type, id);
  if (type === 'customer') showCustomerDetail(id);
  if (type === 'catalog') showCatalogDetail(id);
  if (type === 'site') showSiteDetail(id);
  if (type === 'visit') showVisitDetail(id);
  if (type === 'campaign') showCampaignDetail(id);
  if (type === 'feedback') showFeedbackDetail(id);
}
function campaignPayload(row) { const payload = { name: row.campaign_name, objective: row.objective || null, status: row.status || 'draft', currency: row.currency || 'USD' }; if (row.start_date) payload.start_date = row.start_date; if (row.end_date) payload.end_date = row.end_date; if (row.budget_amount) payload.budget_amount = Number(row.budget_amount); return payload; }
function campaignCriteria(row) { const criteria = {}; if (row.segment) criteria.segment = row.segment; if (row.criteria_key && row.criteria_value) criteria[row.criteria_key] = row.criteria_value; return criteria; }
async function importCampaigns() {
  const button = document.querySelector('#import-campaigns'); button.disabled = true;
  const validationError = validateCampaignRows(pendingCampaigns); if (validationError) throw new Error(validationError);
  const existingCampaigns = await api('marketing', '/api/campaigns'); const existingAudiences = await api('marketing', '/api/audiences'); const existingChannels = await api('marketing', '/api/channels');
  const campaignsByName = new Map(existingCampaigns.map((item) => [item.name, item])); const audiencesByName = new Map(existingAudiences.map((item) => [item.name, item])); const channelsByName = new Map(existingChannels.map((item) => [item.name, item]));
  for (const row of pendingCampaigns) {
    let campaign = campaignsByName.get(row.campaign_name);
    if (!campaign) { campaign = await api('marketing', '/api/campaigns', { method: 'POST', body: JSON.stringify(campaignPayload(row)) }); campaignsByName.set(row.campaign_name, campaign); }
    let audience = audiencesByName.get(row.audience_name);
    if (!audience) { audience = await api('marketing', '/api/audiences', { method: 'POST', body: JSON.stringify({ name: row.audience_name, segment: row.segment || null, criteria: campaignCriteria(row) }) }); audiencesByName.set(row.audience_name, audience); }
    let channel = channelsByName.get(row.channel_name);
    if (!channel) { channel = await api('marketing', '/api/channels', { method: 'POST', body: JSON.stringify({ name: row.channel_name, channel_type: row.channel_type, provider: row.provider || null }) }); channelsByName.set(row.channel_name, channel); }
    await api('marketing', `/api/campaigns/${campaign.campaign_id}/audiences`, { method: 'POST', body: JSON.stringify({ audience_id: audience.audience_id }) });
    await api('marketing', `/api/campaigns/${campaign.campaign_id}/channels`, { method: 'POST', body: JSON.stringify({ channel_id: channel.channel_id, allocation_percent: Number(row.allocation_percent || 0) }) });
  }
  document.querySelector('#campaign-feedback').textContent = `Imported ${pendingCampaigns.length.toLocaleString()} campaign rows.`;
  await loadEngagementData();
}
function renderEngagementData() {
  document.querySelector('#engagement-customer').innerHTML = loadedCustomers.map((customer) => `<option value="${customer.customer_id}">${customer.first_name} ${customer.last_name} · ${customer.email}</option>`).join('') || '<option value="">Load customers first</option>';
  document.querySelector('#engagement-campaign').innerHTML = campaigns.map((campaign) => `<option value="${campaign.campaign_id}">${campaign.name} · ${campaign.status}</option>`).join('') || '<option value="">Import campaigns first</option>';
  document.querySelector('#engagement-channel').innerHTML = '<option value="">No channel selected</option>' + channels.map((channel) => `<option value="${channel.channel_id}">${channel.name} · ${channel.channel_type}</option>`).join('');
  document.querySelector('#campaign-table-body').innerHTML = campaigns.map((campaign) => `<tr class="clickable-row" data-record-type="campaign" data-record-id="${campaign.campaign_id}"><td><strong>${campaign.name}</strong></td><td>${campaign.status}</td><td>${campaign.objective || '-'}</td><td>${campaign.budget_amount == null ? '-' : `${campaign.currency} ${Number(campaign.budget_amount).toLocaleString()}`}</td><td>${new Date(campaign.start_date).toLocaleDateString()}</td></tr>`).join('') || '<tr><td colspan="5" class="table-message">No campaigns found.</td></tr>';
  const campaignNames = new Map(campaigns.map((campaign) => [campaign.campaign_id, campaign.name]));
  document.querySelector('#feedback-table-body').innerHTML = feedbackRecords.slice(-25).reverse().map((record) => `<tr class="clickable-row" data-record-type="feedback" data-record-id="${record.feedback_id}"><td>${customerDetailLabel(record.customer_id)}</td><td>${campaignNames.get(record.campaign_id) || record.campaign_id || '-'}</td><td>${record.source}</td><td>${record.rating}</td><td>${record.sentiment}</td><td>${record.status}</td></tr>`).join('') || '<tr><td colspan="6" class="table-message">No feedback found.</td></tr>';
  document.querySelector('#engagement-state').textContent = `${campaigns.length} campaigns · ${feedbackRecords.length} feedback`;
}
function renderSiteCustomerFilter() {
  const selectedCustomer = document.querySelector('#sites-customer-filter').value || currentCustomerId;
  document.querySelector('#sites-customer-filter').innerHTML = '<option value="">All customers</option>' + loadedCustomers.map((customer) => `<option value="${customer.customer_id}">${customer.first_name} ${customer.last_name} · ${customer.email}</option>`).join('');
  document.querySelector('#sites-customer-filter').value = loadedCustomers.some((customer) => customer.customer_id === selectedCustomer) ? selectedCustomer : '';
}
function renderSiteData() {
  const customerLabels = new Map(loadedCustomers.map((customer) => [customer.customer_id, `${customer.first_name} ${customer.last_name}<br><span class="muted-cell">${customer.email}</span>`]));
  const siteVisitCounts = new Map();
  for (const visit of visits) siteVisitCounts.set(visit.site_id, (siteVisitCounts.get(visit.site_id) || 0) + 1);
  document.querySelector('#site-table-body').innerHTML = sites.map((site) => `<tr class="clickable-row" data-record-type="site" data-record-id="${site.site_id}"><td><strong>${site.name}</strong></td><td>${site.type}</td><td>${site.city || '-'}</td><td>${site.status}</td><td>${siteVisitCounts.get(site.site_id) || 0}</td></tr>`).join('') || '<tr><td colspan="5" class="table-message">No sites found.</td></tr>';
  document.querySelector('#visit-table-body').innerHTML = visits.map((visit) => `<tr class="clickable-row" data-record-type="visit" data-record-id="${visit.visit_id}"><td><strong>${visit.visit_id.slice(0, 8)}</strong></td><td>${customerLabels.get(visit.customer_id) || visit.customer_id}</td><td>${sites.find((site) => site.site_id === visit.site_id)?.name || visit.site_id}</td><td>${visit.channel}</td><td>${formatDateTime(visit.started_at)}</td><td>${formatDateTime(visit.ended_at)}</td></tr>`).join('') || '<tr><td colspan="6" class="table-message">No visits found.</td></tr>';
  document.querySelector('#sites-state').textContent = `${sites.length} sites · ${visits.length} visits`;
}
async function loadSiteData() {
  const selectedCustomer = document.querySelector('#sites-customer-filter') ? document.querySelector('#sites-customer-filter').value : '';
  const [siteList, visitList, customerResult] = await Promise.all([
    api('site', '/api/sites'),
    api('site', selectedCustomer ? `/api/visits?customer_id=${encodeURIComponent(selectedCustomer)}` : '/api/visits'),
    api('crm', '/api/customers?page=1&page_size=100'),
  ]);
  loadedCustomers = customerResult.items;
  sites = siteList;
  visits = visitList;
  renderSiteCustomerFilter();
  renderSiteData();
  document.querySelector('#sites-feedback').textContent = 'Site and visit records loaded.';
}
function renderEventData() {
  document.querySelector('#events-table-body').innerHTML = events.map((event) => `<tr class="clickable-row" data-record-type="event" data-record-id="${event.event_id}"><td>${formatDateTime(event.recorded_at)}</td><td><strong>${event.event_type}</strong></td><td>${event.source_service}</td><td>${event.aggregate_type} · ${event.aggregate_id.slice(0, 8)}</td><td>${event.correlation_id || '-'}</td><td><code>${JSON.stringify(event.payload)}</code></td></tr>`).join('') || '<tr><td colspan="6" class="table-message">No events found.</td></tr>';
  document.querySelector('#events-state').textContent = `${events.length} events`;
  if (document.querySelector('.tab.active')?.dataset.tab === 'events') activateLeftSidebar('events');
}
async function loadEventData() {
  const correlationId = document.querySelector('#events-correlation-filter').value.trim();
  events = await api('events', `/api/events?limit=100${correlationId ? `&correlation_id=${encodeURIComponent(correlationId)}` : ''}`);
  renderEventData();
  document.querySelector('#events-feedback').textContent = 'Event records loaded.';
}
async function loadEngagementData() {
  const result = await api('crm', '/api/customers?page=1&page_size=100'); loadedCustomers = result.items; renderJourneyCustomers();
  [campaigns, channels, feedbackRecords] = await Promise.all([api('marketing', '/api/campaigns'), api('marketing', '/api/channels'), api('feedback', '/api/feedback')]);
  renderEngagementData();
  if (currentCustomerId && loadedCustomers.some((customer) => customer.customer_id === currentCustomerId)) document.querySelector('#engagement-customer').value = currentCustomerId;
  document.querySelector('#engagement-feedback').textContent = 'Marketing and feedback services connected.';
}
async function simulateMarketingTouch() {
  const customerId = document.querySelector('#engagement-customer').value; const campaignId = document.querySelector('#engagement-campaign').value; const channelId = document.querySelector('#engagement-channel').value || null; const eventType = document.querySelector('#marketing-event').value;
  if (!customerId || !campaignId) throw new Error('Select a customer and campaign first.');
  const interaction = await api('marketing', `/api/campaigns/${campaignId}/interactions`, { method: 'POST', body: JSON.stringify({ customer_id: customerId, event_type: eventType, channel_id: channelId, detail: 'simulator_manual_touch' }) });
  document.querySelector('#marketing-flow-feedback').textContent = `Recorded ${interaction.event_type} for ${customerId}.`;
}
async function submitFeedback() {
  const customerId = document.querySelector('#engagement-customer').value; const campaignId = document.querySelector('#engagement-campaign').value || null; const rating = Math.min(5, Math.max(1, Number(document.querySelector('#feedback-rating').value) || 1));
  if (!customerId) throw new Error('Select a customer first.');
  const payload = { customer_id: customerId, campaign_id: campaignId, source: document.querySelector('#feedback-source').value, rating, sentiment: document.querySelector('#feedback-sentiment').value, comment: document.querySelector('#feedback-comment').value || null };
  const record = await api('feedback', '/api/feedback', { method: 'POST', body: JSON.stringify(payload) });
  document.querySelector('#feedback-flow-feedback').textContent = `Feedback ${record.feedback_id.slice(0, 8)} submitted.`;
  await loadEngagementData();
}
function randomItem(items) {
  return items[Math.floor(Math.random() * items.length)];
}
function simulatedFeedbackPayload(customerId, campaignId) {
  const sentimentPatterns = {
    positive: { ratings: [4, 5], comments: ['Offer arrived at the right moment and felt relevant.', 'The campaign made it easy to find what I needed.', 'Helpful message with a clear next step.'] },
    neutral: { ratings: [3, 4], comments: ['Useful enough, but not especially memorable.', 'The message was clear, though the timing was average.', 'I understood the promotion but did not act on it.'] },
    negative: { ratings: [1, 2], comments: ['The recommendation did not match what I usually buy.', 'The campaign repeated too often for my preferences.', 'The message felt unrelated to my current need.'] },
    mixed: { ratings: [2, 3, 4], comments: ['Interesting promotion, though the product match was only partial.', 'The offer was good, but the channel was not ideal.', 'Some details helped, but I wanted clearer terms.'] },
    unknown: { ratings: [3], comments: ['No clear sentiment captured from this response.', 'Short response with limited context.', 'Customer left a rating without much detail.'] },
  };
  const source = randomItem(['survey', 'web', 'mobile', 'store', 'support', 'social']);
  const sentiment = randomItem(Object.keys(sentimentPatterns));
  const pattern = sentimentPatterns[sentiment];
  return { customer_id: customerId, campaign_id: campaignId || null, source, rating: randomItem(pattern.ratings), sentiment, comment: randomItem(pattern.comments), status: 'submitted' };
}
async function simulateFeedback() {
  const selectedCustomerId = document.querySelector('#engagement-customer').value; const selectedCampaignId = document.querySelector('#engagement-campaign').value || null;
  const size = Math.min(250, Math.max(1, Number(document.querySelector('#feedback-batch-size').value) || 1));
  const availableCustomers = loadedCustomers.length ? loadedCustomers.map((customer) => customer.customer_id) : [selectedCustomerId].filter(Boolean);
  const availableCampaigns = campaigns.length ? campaigns.map((campaign) => campaign.campaign_id) : [selectedCampaignId].filter(Boolean);
  if (!availableCustomers.length) throw new Error('Load customers before simulating feedback.');
  const counts = { positive: 0, neutral: 0, negative: 0, mixed: 0, unknown: 0 };
  for (let index = 0; index < size; index += 1) {
    const payload = simulatedFeedbackPayload(randomItem(availableCustomers), availableCampaigns.length ? randomItem(availableCampaigns) : null);
    const record = await api('feedback', '/api/feedback', { method: 'POST', body: JSON.stringify(payload) });
    await recordEvent('feedback', 'FeedbackSubmitted', 'feedback', record.feedback_id, { customer_id: record.customer_id, campaign_id: record.campaign_id, rating: record.rating, sentiment: record.sentiment });
    counts[record.sentiment] += 1;
    document.querySelector('#feedback-flow-feedback').textContent = `Simulated ${index + 1} of ${size} feedback records.`;
  }
  document.querySelector('#feedback-flow-feedback').textContent = `Simulated ${size} feedback records · ${counts.positive} positive · ${counts.neutral} neutral · ${counts.negative} negative · ${counts.mixed} mixed · ${counts.unknown} unknown.`;
  await loadEngagementData();
}
async function simulateEngagementBatch() {
  const size = Math.min(100, Math.max(1, Number(document.querySelector('#engagement-batch-size').value) || 1));
  if (!loadedCustomers.length || !campaigns.length) throw new Error('Load customers and campaigns first.');
  const events = ['sent', 'delivered', 'opened', 'clicked', 'converted', 'opted_out']; const sentiments = ['positive', 'neutral', 'negative', 'mixed'];
  for (let index = 0; index < size; index += 1) {
    const customer = loadedCustomers[Math.floor(Math.random() * loadedCustomers.length)]; const campaign = campaigns[Math.floor(Math.random() * campaigns.length)]; const channel = channels[Math.floor(Math.random() * channels.length)]; const eventType = events[Math.floor(Math.random() * events.length)];
    const interaction = await api('marketing', `/api/campaigns/${campaign.campaign_id}/interactions`, { method: 'POST', body: JSON.stringify({ customer_id: customer.customer_id, event_type: eventType, channel_id: channel?.channel_id || null, detail: 'simulator_batch_touch' }) });
    await recordEvent('marketing', 'CampaignInteractionRecorded', 'campaign_interaction', interaction.interaction_id, { customer_id: customer.customer_id, campaign_id: campaign.campaign_id, event_type: eventType });
    if (Math.random() < 0.4) { const feedback = await api('feedback', '/api/feedback', { method: 'POST', body: JSON.stringify({ customer_id: customer.customer_id, campaign_id: campaign.campaign_id, source: 'survey', rating: 1 + Math.floor(Math.random() * 5), sentiment: sentiments[Math.floor(Math.random() * sentiments.length)], comment: `Batch ${eventType} response for ${campaign.name}` }) }); await recordEvent('feedback', 'FeedbackSubmitted', 'feedback', feedback.feedback_id, { customer_id: feedback.customer_id, campaign_id: feedback.campaign_id, rating: feedback.rating, sentiment: feedback.sentiment }); }
    document.querySelector('#marketing-flow-feedback').textContent = `Simulated ${index + 1} of ${size} engagement records.`;
  }
  await loadEngagementData();
}

customerSelect.addEventListener('change', () => syncCurrentCustomer(customerSelect.value));
storeSelect.addEventListener('change', () => loadStoreCatalog().catch((error) => { feedbackElement.textContent = error.message; }));
document.querySelector('#start-journey').addEventListener('click', () => startVisit().catch((error) => { feedbackElement.textContent = error.message; }));
document.querySelectorAll('[data-outcome]').forEach((button) => button.addEventListener('click', () => completeOutcome(button.dataset.outcome).catch((error) => { feedbackElement.textContent = error.message; })));
document.querySelector('#simulate-batch').addEventListener('click', () => simulateBatch().catch((error) => { feedbackElement.textContent = error.message; }));
document.querySelectorAll('[data-tab]').forEach((button) => button.addEventListener('click', () => { document.querySelector('#record-detail-panel').hidden = true; document.querySelectorAll('[data-tab]').forEach((tab) => tab.classList.toggle('active', tab === button)); document.querySelectorAll('.view').forEach((view) => { view.hidden = view.id !== `${button.dataset.tab}-view`; }); activateLeftSidebar(button.dataset.tab); if (button.dataset.tab === 'customers') loadCustomers().catch(() => {}); if (button.dataset.tab === 'orders') loadCartOrderData().catch((error) => { document.querySelector('#orders-feedback').textContent = error.message; }); if (button.dataset.tab === 'catalog') loadCatalogDirectory().catch((error) => { document.querySelector('#catalog-directory-feedback').textContent = error.message; }); if (button.dataset.tab === 'sites') loadSiteData().catch((error) => { document.querySelector('#sites-feedback').textContent = error.message; }); if (button.dataset.tab === 'engagement') loadEngagementData().catch((error) => { document.querySelector('#engagement-feedback').textContent = error.message; }); if (button.dataset.tab === 'events') loadEventData().catch((error) => { document.querySelector('#events-feedback').textContent = error.message; }); }));
document.querySelector('#load-default-csv').addEventListener('click', () => loadBundledCsv().catch((error) => { document.querySelector('#customer-feedback').textContent = error.message; }));
document.querySelector('#customer-file').addEventListener('change', (event) => { if (event.target.files[0]) event.target.files[0].text().then((text) => showCustomerPreview(parseCsv(text))); });
document.querySelector('#import-customers').addEventListener('click', () => importCustomers().catch((error) => { document.querySelector('#customer-feedback').textContent = error.message; }));
document.querySelector('#load-default-catalog').addEventListener('click', () => loadBundledCatalog().catch((error) => { document.querySelector('#catalog-feedback').textContent = error.message; }));
document.querySelector('#catalog-file').addEventListener('change', (event) => { if (event.target.files[0]) event.target.files[0].text().then((text) => showCatalogPreview(parseCsv(text))); });
document.querySelector('#import-catalog').addEventListener('click', () => importCatalog().catch((error) => { document.querySelector('#catalog-feedback').textContent = error.message; }));
document.querySelector('#load-default-campaigns').addEventListener('click', () => loadBundledCampaigns().catch((error) => { document.querySelector('#campaign-feedback').textContent = error.message; }));
document.querySelector('#campaign-file').addEventListener('change', (event) => { if (event.target.files[0]) { document.querySelector('#campaign-file-name').textContent = event.target.files[0].name; event.target.files[0].text().then((text) => showCampaignPreview(parseCsv(text))); } });
document.querySelector('#import-campaigns').addEventListener('click', () => importCampaigns().catch((error) => { document.querySelector('#campaign-feedback').textContent = error.message; }));
document.querySelector('#simulate-marketing-touch').addEventListener('click', () => simulateMarketingTouch().catch((error) => { document.querySelector('#marketing-flow-feedback').textContent = error.message; }));
document.querySelector('#submit-feedback').addEventListener('click', () => submitFeedback().catch((error) => { document.querySelector('#feedback-flow-feedback').textContent = error.message; }));
document.querySelector('#simulate-feedback').addEventListener('click', () => simulateFeedback().catch((error) => { document.querySelector('#feedback-flow-feedback').textContent = error.message; }));
document.querySelector('#simulate-engagement-batch').addEventListener('click', () => simulateEngagementBatch().catch((error) => { document.querySelector('#marketing-flow-feedback').textContent = error.message; }));
document.querySelector('#simulate-user-visits').addEventListener('click', () => simulateUserVisits().catch((error) => { document.querySelector('#user-visits-feedback').textContent = error.message; }));
document.querySelector('#refresh-engagement').addEventListener('click', () => loadEngagementData().catch((error) => { document.querySelector('#engagement-feedback').textContent = error.message; }));
document.querySelector('#refresh-sites').addEventListener('click', () => loadSiteData().catch((error) => { document.querySelector('#sites-feedback').textContent = error.message; }));
document.querySelector('#sites-customer-filter').addEventListener('change', () => loadSiteData().catch((error) => { document.querySelector('#sites-feedback').textContent = error.message; }));
document.querySelector('#refresh-events').addEventListener('click', () => loadEventData().catch((error) => { document.querySelector('#events-feedback').textContent = error.message; }));
document.querySelector('#events-correlation-filter').addEventListener('change', () => loadEventData().catch((error) => { document.querySelector('#events-feedback').textContent = error.message; }));
document.querySelector('#refresh-customers').addEventListener('click', () => loadCustomers().catch(() => {}));
document.querySelector('#refresh-orders').addEventListener('click', () => loadCartOrderData().catch((error) => { document.querySelector('#orders-feedback').textContent = error.message; }));
document.querySelector('#orders-customer-filter').addEventListener('change', () => { syncCurrentCustomer(document.querySelector('#orders-customer-filter').value); loadCartOrderData().catch((error) => { document.querySelector('#orders-feedback').textContent = error.message; }); });
document.querySelector('#orders-start-date').addEventListener('change', () => loadCartOrderData().catch((error) => { document.querySelector('#orders-feedback').textContent = error.message; }));
document.querySelector('#orders-end-date').addEventListener('change', () => loadCartOrderData().catch((error) => { document.querySelector('#orders-feedback').textContent = error.message; }));
document.querySelector('#cart-table-body').addEventListener('click', (event) => { const row = event.target.closest('[data-record-type]'); if (row) showTableDetail(row.dataset.recordType, row.dataset.recordId); });
document.querySelector('#order-table-body').addEventListener('click', (event) => { const row = event.target.closest('[data-record-type]'); if (row) showTableDetail(row.dataset.recordType, row.dataset.recordId); });
document.querySelector('#customer-table-body').addEventListener('click', (event) => { const row = event.target.closest('[data-record-type]'); if (row) showTableDetail(row.dataset.recordType, row.dataset.recordId); });
document.querySelector('#catalog-table-body').addEventListener('click', (event) => { const row = event.target.closest('[data-record-type]'); if (row) showTableDetail(row.dataset.recordType, row.dataset.recordId); });
document.querySelector('#site-table-body').addEventListener('click', (event) => { const row = event.target.closest('[data-record-type]'); if (row) showTableDetail(row.dataset.recordType, row.dataset.recordId); });
document.querySelector('#visit-table-body').addEventListener('click', (event) => { const row = event.target.closest('[data-record-type]'); if (row) showTableDetail(row.dataset.recordType, row.dataset.recordId); });
document.querySelector('#campaign-table-body').addEventListener('click', (event) => { const row = event.target.closest('[data-record-type]'); if (row) showTableDetail(row.dataset.recordType, row.dataset.recordId); });
document.querySelector('#feedback-table-body').addEventListener('click', (event) => { const row = event.target.closest('[data-record-type]'); if (row) showTableDetail(row.dataset.recordType, row.dataset.recordId); });
document.querySelector('#close-record-detail').addEventListener('click', () => { document.querySelector('#record-detail-panel').hidden = true; });
document.querySelector('#catalog-store-filter').addEventListener('change', () => loadCatalogDirectory().catch((error) => { document.querySelector('#catalog-directory-feedback').textContent = error.message; }));
document.querySelector('#engagement-customer').addEventListener('change', () => syncCurrentCustomer(document.querySelector('#engagement-customer').value));
document.querySelector('#refresh-catalog').addEventListener('click', () => loadCatalogDirectory().catch((error) => { document.querySelector('#catalog-directory-feedback').textContent = error.message; }));
document.querySelector('#previous-customers').addEventListener('click', () => { if (customerPage > 1) { customerPage -= 1; loadCustomers(); } });
document.querySelector('#next-customers').addEventListener('click', () => { if (customerPage < customerTotalPages) { customerPage += 1; loadCustomers(); } });
document.querySelector('#customer-search').addEventListener('input', () => { customerPage = 1; window.clearTimeout(window.customerSearchTimer); window.customerSearchTimer = window.setTimeout(() => loadCustomers(), 250); });
renderSteps();
activateLeftSidebar('journey');
loadJourneyData();
