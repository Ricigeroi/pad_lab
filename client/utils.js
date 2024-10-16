// utils.js
function showNotification(message, type = 'error') {
    const notificationsDiv = document.getElementById('notifications');
    
    const notification = document.createElement('div');
    notification.classList.add('notification');
    if (type === 'success') {
        notification.classList.add('success');
    }

    // Добавить сообщение
    notification.textContent = message;

    // Добавить кнопку закрытия
    const closeBtn = document.createElement('span');
    closeBtn.classList.add('close-btn');
    closeBtn.innerHTML = '&times;';
    closeBtn.onclick = () => {
        notificationsDiv.removeChild(notification);
    };
    notification.appendChild(closeBtn);

    notificationsDiv.appendChild(notification);

    // Автоматически удалить уведомление через 5 секунд
    setTimeout(() => {
        if (notificationsDiv.contains(notification)) {
            notificationsDiv.removeChild(notification);
        }
    }, 5000);
}
