/**
 * Line Ranger ID Store - Main JavaScript
 */

// ===== Alert System =====
function showAlert(message, type = 'success') {
    const container = document.querySelector('.alert-container') || createAlertContainer();
    
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = `
        <span class="alert-icon">${getAlertIcon(type)}</span>
        <span class="alert-message">${message}</span>
    `;
    
    container.appendChild(alert);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        alert.remove();
    }, 5000);
}

function createAlertContainer() {
    const container = document.createElement('div');
    container.className = 'alert-container';
    document.body.appendChild(container);
    return container;
}

function getAlertIcon(type) {
    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };
    return icons[type] || icons.info;
}

// ===== Modal System =====
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
        document.body.style.overflow = '';
    }
});

// Close modal on ESC key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const activeModal = document.querySelector('.modal-overlay.active');
        if (activeModal) {
            activeModal.classList.remove('active');
            document.body.style.overflow = '';
        }
    }
});

// ===== Form Validation =====
function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return true;
    
    let isValid = true;
    const requiredFields = form.querySelectorAll('[required]');
    
    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            isValid = false;
            field.classList.add('invalid');
            showAlert(`กรุณากรอก ${field.name || 'ข้อมูล'}`, 'error');
        } else {
            field.classList.remove('invalid');
        }
    });
    
    return isValid;
}

// ===== Buy Product Modal =====
function openBuyModal(productId, productName) {
    const modal = document.getElementById('buyModal');
    if (!modal) return;
    
    // Set product info
    document.getElementById('modal-product-name').textContent = productName;
    document.getElementById('modal-product-id').value = productId;
    
    openModal('buyModal');
}

// ===== Admin: Link ID =====
async function linkId(orderId) {
    const btn = event.target;
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> กำลังดำเนินการ...';
    
    try {
        const response = await fetch(`/admin/order/${orderId}/link`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert(data.message, 'success');
            
            // Show customer credentials
            if (data.order_info) {
                showCredentialsModal(data.order_info);
            }
            
            // Reload page after 2 seconds
            setTimeout(() => {
                location.reload();
            }, 2000);
        } else {
            showAlert(data.message, 'error');
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    } catch (error) {
        showAlert('เกิดข้อผิดพลาดในการเชื่อมต่อ', 'error');
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

function showCredentialsModal(info) {
    const modal = document.getElementById('credentialsModal');
    if (!modal) return;
    
    document.getElementById('cred-method').textContent = info.link_method === 'google' ? 'Google' : 'LINE';
    document.getElementById('cred-id').textContent = info.customer_id;
    document.getElementById('cred-pass').textContent = info.customer_pass;
    
    openModal('credentialsModal');
}

// ===== Admin: Update Order Status =====
async function updateOrderStatus(orderId, newStatus) {
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = `/admin/order/${orderId}/update`;
    
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'status';
    input.value = newStatus;
    
    form.appendChild(input);
    document.body.appendChild(form);
    form.submit();
}

// ===== Admin: Delete Product Confirmation =====
function confirmDelete(productId, productName) {
    if (confirm(`คุณต้องการลบสินค้า "${productName}" ใช่หรือไม่?`)) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/admin/product/${productId}/delete`;
        document.body.appendChild(form);
        form.submit();
    }
}

// ===== Image Preview =====
function previewImage(input, previewId) {
    const preview = document.getElementById(previewId);
    if (!preview) return;
    
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = (e) => {
            preview.src = e.target.result;
            preview.style.display = 'block';
        };
        reader.readAsDataURL(input.files[0]);
    }
}

// ===== Toggle Password Visibility =====
function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    
    input.type = input.type === 'password' ? 'text' : 'password';
}

// ===== Copy to Clipboard =====
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showAlert('คัดลอกแล้ว!', 'success');
    }).catch(() => {
        showAlert('ไม่สามารถคัดลอกได้', 'error');
    });
}

// ===== Initialize Flash Messages =====
document.addEventListener('DOMContentLoaded', () => {
    // Flash messages from server
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(msg => {
        showAlert(msg.dataset.message, msg.dataset.type);
        msg.remove();
    });
    
    // Add animation to cards on scroll
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate-in');
            }
        });
    }, { threshold: 0.1 });
    
    document.querySelectorAll('.card').forEach(card => {
        observer.observe(card);
    });
});

// ===== Navbar Scroll Effect =====
window.addEventListener('scroll', () => {
    const navbar = document.querySelector('.navbar');
    if (navbar) {
        if (window.scrollY > 50) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
    }
});
