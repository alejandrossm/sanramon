// Comportamientos globales de la interfaz.
// Este archivo se carga en todas las paginas que extienden base.html.
document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.querySelector('[data-sidebar]');
    const sidebarToggle = document.querySelector('[data-sidebar-toggle]');
    const sidebarPanel = document.querySelector('[data-sidebar-panel]');
    const sidebarToggleLabel = document.querySelector('[data-sidebar-toggle-label]');
    const mobileSidebarQuery = window.matchMedia('(max-width: 991.98px)');

    // Controla apertura y cierre del sidebar en pantallas moviles.
    const setSidebarOpen = (isOpen) => {
        if (!sidebar || !sidebarToggle) {
            return;
        }

        sidebar.dataset.sidebarOpen = isOpen ? 'true' : 'false';
        sidebarToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        if (sidebarToggleLabel) {
            sidebarToggleLabel.textContent = isOpen ? 'Cerrar menu' : 'Abrir menu';
        }
    };

    if (sidebar && sidebarToggle && sidebarPanel) {
        setSidebarOpen(false);
        sidebarToggle.addEventListener('click', () => {
            setSidebarOpen(sidebar.dataset.sidebarOpen !== 'true');
        });

        sidebarPanel.querySelectorAll('a').forEach((link) => {
            link.addEventListener('click', () => {
                if (mobileSidebarQuery.matches) {
                    setSidebarOpen(false);
                }
            });
        });

        mobileSidebarQuery.addEventListener('change', () => {
            setSidebarOpen(false);
        });
    }

    if (window.Swal) {
        const iconByLevel = {
            success: 'success',
            error: 'error',
            danger: 'error',
            warning: 'warning',
            info: 'info',
        };
        const titleByLevel = {
            success: 'Operacion completada',
            error: 'No se pudo completar',
            danger: 'No se pudo completar',
            warning: 'Atencion',
            info: 'Informacion',
        };

        // Convierte mensajes Django renderizados en alertas SweetAlert.
        document.querySelectorAll('[data-app-message]').forEach((message) => {
            const level = message.dataset.messageLevel || 'info';
            const text = message.dataset.messageText || message.textContent.trim();

            if (!text) {
                return;
            }

            Swal.fire({
                icon: iconByLevel[level] || 'info',
                title: titleByLevel[level] || 'Informacion',
                text,
                confirmButtonText: 'Aceptar',
                confirmButtonColor: '#2f5d50',
            });
        });

        // Intercepta formularios destructivos o sensibles para pedir confirmacion.
        document.querySelectorAll('[data-confirm-submit]').forEach((form) => {
            form.addEventListener('submit', (event) => {
                if (form.dataset.confirmed === 'true') {
                    return;
                }

                event.preventDefault();

                Swal.fire({
                    title: form.dataset.confirmTitle || 'Confirmar accion',
                    text: form.dataset.confirmText || 'Esta accion se aplicara inmediatamente.',
                    icon: form.dataset.confirmIcon || 'warning',
                    showCancelButton: true,
                    confirmButtonText: form.dataset.confirmButton || 'Confirmar',
                    cancelButtonText: form.dataset.cancelButton || 'Cancelar',
                    confirmButtonColor: form.dataset.confirmColor || '#2f5d50',
                    cancelButtonColor: '#5d6b74',
                }).then((result) => {
                    if (result.isConfirmed) {
                        form.dataset.confirmed = 'true';
                        form.submit();
                    }
                });
            });
        });
    }

    const setDeleteButtonVariant = (button, variantClasses) => {
        button.classList.remove('btn-danger', 'btn-outline-danger', 'btn-outline-secondary', 'text-muted');
        button.classList.add(...variantClasses);
    };

    // Habilita o deshabilita visualmente los botones de eliminacion masiva/manual.
    const setDeleteButtonsEnabled = (enabled) => {
        document
            .querySelectorAll('[data-delete-user-button][data-delete-allowed="true"]')
            .forEach((button) => {
                button.disabled = !enabled;
                setDeleteButtonVariant(
                    button,
                    enabled ? ['btn-danger'] : ['btn-outline-secondary', 'text-muted']
                );
            });

        document
            .querySelectorAll('[data-delete-unavailable-button]')
            .forEach((button) => {
                button.disabled = true;
                setDeleteButtonVariant(
                    button,
                    enabled ? ['btn-outline-danger'] : ['btn-outline-secondary', 'text-muted']
                );
            });
    };

    document.querySelectorAll('[data-enable-delete-column]').forEach((toggle) => {
        const isCheckboxSwitch = toggle.matches('input[type="checkbox"]');
        const labelContainer = toggle.closest('.form-check') || toggle;
        const label = labelContainer.querySelector('[data-delete-toggle-label]');

        const setToggleState = (enabled) => {
            toggle.dataset.deleteEnabled = enabled ? 'true' : 'false';
            if (isCheckboxSwitch) {
                toggle.checked = enabled;
                toggle.setAttribute('aria-checked', enabled ? 'true' : 'false');
            } else {
                toggle.setAttribute('aria-pressed', enabled ? 'true' : 'false');
            }
            const text = enabled
                ? toggle.dataset.disableDeleteLabel || 'Desactivar eliminacion'
                : toggle.dataset.enableDeleteLabel || 'Activar eliminacion';
            if (label) {
                label.textContent = text;
            } else {
                toggle.textContent = text;
            }
            setDeleteButtonsEnabled(enabled);
        };

        setToggleState(toggle.dataset.deleteEnabled === 'true');

        const handleToggle = () => {
            const shouldEnable = isCheckboxSwitch ? toggle.checked : toggle.dataset.deleteEnabled !== 'true';

            if (!shouldEnable) {
                setToggleState(false);
                return;
            }

            const activateDeletion = () => {
                setToggleState(true);
            };

            activateDeletion();

            if (!window.Swal) {
                window.alert(toggle.dataset.enableDeleteText || 'Eliminacion activada.');
                return;
            }

            Swal.fire({
                icon: 'warning',
                title: toggle.dataset.enableDeleteTitle || 'Eliminacion activada',
                text: toggle.dataset.enableDeleteText || 'La eliminacion quedo habilitada.',
                confirmButtonText: 'Aceptar',
                confirmButtonColor: '#b42318',
            });
        };

        toggle.addEventListener(isCheckboxSwitch ? 'change' : 'click', handleToggle);
    });

    // Formatea RUT chileno mientras el usuario escribe.
    const cleanRut = (value) => value
        .toUpperCase()
        .replace(/[^0-9K]/g, '')
        .slice(0, 9);

    const formatRut = (value) => {
        const cleanValue = cleanRut(value);
        if (cleanValue.length <= 1) {
            return cleanValue;
        }

        const body = cleanValue.slice(0, -1);
        const verifier = cleanValue.slice(-1);
        const formattedBody = body.replace(/\B(?=(\d{3})+(?!\d))/g, '.');

        return `${formattedBody}-${verifier}`;
    };

    document.querySelectorAll('[data-rut-format]').forEach((input) => {
        input.value = formatRut(input.value);

        input.addEventListener('input', () => {
            input.value = formatRut(input.value);
            input.setSelectionRange(input.value.length, input.value.length);
        });
    });

    document.querySelectorAll('[data-rut-scan-trigger]').forEach((button) => {
        const target = document.querySelector(button.dataset.rutScanTarget || '[data-rut-scan-input]');

        if (!target) {
            return;
        }

        button.addEventListener('click', () => {
            target.value = '';
            target.focus();
            target.select();
        });
    });

    const rutScanInput = document.querySelector('[data-rut-scan-input]');
    if (rutScanInput && document.activeElement === document.body) {
        rutScanInput.focus();
    }

    // Mantiene telefonos moviles chilenos con prefijo +56 y 9 digitos locales.
    const formatPhoneWithPrefix = (value, prefix) => {
        const digits = value.replace(/\D/g, '');
        let localDigits = digits;

        if (localDigits.startsWith('56')) {
            localDigits = localDigits.slice(2);
        }

        return `${prefix}${localDigits.slice(0, 9)}`;
    };

    document.querySelectorAll('[data-phone-prefix]').forEach((input) => {
        const prefix = input.dataset.phonePrefix || '+56';

        input.value = formatPhoneWithPrefix(input.value || prefix, prefix);

        input.addEventListener('focus', () => {
            if (!input.value.startsWith(prefix)) {
                input.value = prefix;
            }
            input.setSelectionRange(input.value.length, input.value.length);
        });

        input.addEventListener('input', () => {
            input.value = formatPhoneWithPrefix(input.value, prefix);
            input.setSelectionRange(input.value.length, input.value.length);
        });

        input.addEventListener('keydown', (event) => {
            const cursorAtPrefix = input.selectionStart <= prefix.length;
            const deletingPrefix = (
                (event.key === 'Backspace' && cursorAtPrefix)
                || (event.key === 'Delete' && input.selectionStart < prefix.length)
            );

            if (deletingPrefix) {
                event.preventDefault();
                input.setSelectionRange(prefix.length, prefix.length);
            }
        });
    });
});
