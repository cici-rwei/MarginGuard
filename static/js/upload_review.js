/* Optional acceptance bootstrap. Never put the review key in URLs or storage. */
'use strict';
(function () {
  const form = document.getElementById('upload-review-form');
  if (!form) return;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const input = document.getElementById('upload-review-key');
    const status = document.getElementById('upload-review-status');
    const button = form.querySelector('button');
    const key = input.value.trim();
    input.value = '';
    if (!/^[a-f0-9]{64}$/.test(key)) {
      status.textContent = 'Enter the complete temporary review key supplied by the test organiser.';
      return;
    }
    button.disabled = true;
    status.textContent = 'Checking controlled test access…';
    try {
      const response = await fetch('/api/business/session', {
        method: 'GET', credentials: 'same-origin', cache: 'no-store',
        redirect: 'error', referrerPolicy: 'no-referrer',
        headers: { 'X-Upload-Review-Key': key }
      });
      if (!response.ok) {
        status.textContent = response.status === 503
          ? 'This controlled test is unavailable or has ended. Synthetic Demo remains available.'
          : 'The review key was not accepted. Check it with the test organiser and try again.';
        return;
      }
      location.replace('/?mode=business');
    } catch (_) {
      status.textContent = 'Could not reach the secure service. Check your connection and re-enter the key to retry.';
    } finally {
      input.value = '';
      button.disabled = false;
    }
  });
})();
