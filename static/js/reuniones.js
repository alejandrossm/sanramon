// Comportamientos propios del formulario de reuniones.
// Se carga solo en crear_reunion.html para no mezclar reglas de dominio en base.html.
document.addEventListener('DOMContentLoaded', () => {
    const SUBMIT_LOCK_TIMEOUT_MS = 8000;

    const lockFormSubmitWhileNavigating = (form) => {
        if (!form || !form.dataset || form.dataset.reunionSubmitLockReady === 'true') {
            return;
        }

        form.dataset.reunionSubmitLockReady = 'true';
        form.addEventListener('submit', (event) => {
            if (form.dataset.reunionSubmitting === 'true') {
                event.preventDefault();
                return;
            }

            form.dataset.reunionSubmitting = 'true';
            form.setAttribute('aria-busy', 'true');

            const submitButtons = form.querySelectorAll(
                'button[type="submit"], input[type="submit"]',
            );
            submitButtons.forEach((button) => {
                button.disabled = true;
                if (button.tagName === 'INPUT') {
                    button.dataset.originalValue = button.value;
                    button.value = 'Guardando...';
                } else {
                    button.dataset.originalText = button.textContent;
                    button.textContent = 'Guardando...';
                }
            });

            window.setTimeout(() => {
                form.dataset.reunionSubmitting = 'false';
                form.removeAttribute('aria-busy');
                submitButtons.forEach((button) => {
                    button.disabled = false;
                    if (button.tagName === 'INPUT' && button.dataset.originalValue) {
                        button.value = button.dataset.originalValue;
                    } else if (button.dataset.originalText) {
                        button.textContent = button.dataset.originalText;
                    }
                });
            }, SUBMIT_LOCK_TIMEOUT_MS);
        });
    };

    document.querySelectorAll('[data-reunion-date]').forEach((dateInput) => {
        const form = dateInput.closest('form') || document;
        const timeInput = form.querySelector('[data-reunion-time]');
        const statusSelect = form.querySelector('[data-reunion-status]');

        if (!statusSelect) {
            return;
        }

        lockFormSubmitWhileNavigating(form);

        const historicalValue = statusSelect.dataset.historicalValue;
        const getHiddenStatusInput = () => form.querySelector('[data-reunion-status-hidden]');
        const ensureHiddenStatusInput = () => {
            let hiddenStatusInput = getHiddenStatusInput();

            if (!hiddenStatusInput) {
                hiddenStatusInput = document.createElement('input');
                hiddenStatusInput.type = 'hidden';
                hiddenStatusInput.name = statusSelect.name;
                hiddenStatusInput.dataset.reunionStatusHidden = 'true';
                statusSelect.insertAdjacentElement('afterend', hiddenStatusInput);
            }

            hiddenStatusInput.value = historicalValue;
        };
        const removeHiddenStatusInput = () => {
            const hiddenStatusInput = getHiddenStatusInput();

            if (hiddenStatusInput) {
                hiddenStatusInput.remove();
            }
        };
        const meetingIsPast = () => {
            const today = dateInput.dataset.today;
            const currentTime = timeInput ? timeInput.dataset.currentTime : '';

            if (!dateInput.value || !today || !historicalValue) {
                return false;
            }

            if (dateInput.value < today) {
                return true;
            }

            return (
                dateInput.value === today
                && Boolean(timeInput && timeInput.value && currentTime)
                && timeInput.value < currentTime
            );
        };
        const syncMeetingStatusWithDateTime = () => {
            if (!dateInput.value || !historicalValue) {
                statusSelect.disabled = false;
                statusSelect.removeAttribute('aria-disabled');
                removeHiddenStatusInput();
                return;
            }

            // Fechas y horas pasadas siempre se fuerzan como historicas y bloquean el cambio manual.
            if (meetingIsPast()) {
                if (statusSelect.value !== historicalValue) {
                    statusSelect.value = historicalValue;
                    statusSelect.dispatchEvent(new Event('change', { bubbles: true }));
                }
                statusSelect.disabled = true;
                statusSelect.setAttribute('aria-disabled', 'true');
                // Un select deshabilitado no se envia en el POST; este hidden conserva el valor.
                ensureHiddenStatusInput();
                return;
            }

            // Desde el momento actual en adelante el estado vuelve a ser editable.
            statusSelect.disabled = false;
            statusSelect.removeAttribute('aria-disabled');
            removeHiddenStatusInput();
        };

        syncMeetingStatusWithDateTime();
        dateInput.addEventListener('input', syncMeetingStatusWithDateTime);
        dateInput.addEventListener('change', syncMeetingStatusWithDateTime);
        if (timeInput) {
            timeInput.addEventListener('input', syncMeetingStatusWithDateTime);
            timeInput.addEventListener('change', syncMeetingStatusWithDateTime);
        }
        statusSelect.addEventListener('change', syncMeetingStatusWithDateTime);
    });
});
