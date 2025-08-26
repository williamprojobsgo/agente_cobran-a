function toggleChat() {
    const popup = document.getElementById('chatPopup');
    const notification = document.getElementById('notification');
  
    if (popup.style.display === 'none' || popup.style.display === '') {
      popup.style.display = 'flex';
    } else {
      popup.style.display = 'none';
    }
  
    // Esconde notificação depois de clicar
    notification.style.display = 'none';
  }
  
  function sendMessage() {
    const userInput = document.getElementById('userMessage').value.trim();
    const chatBody = document.querySelector('.chat-body');
  
    if (userInput !== '') {
      // Adiciona a mensagem no chat
      const userMessage = document.createElement('p');
      userMessage.innerHTML = `<strong>Você:</strong> ${userInput}`;
      chatBody.appendChild(userMessage);
  
      // Limpa o campo
      document.getElementById('userMessage').value = '';
  
      // Scroll automático para baixo
      chatBody.scrollTop = chatBody.scrollHeight;
    } else {
      alert('Por favor, digite uma solicitação.');
    }
  }
  