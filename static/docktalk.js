// DockTalk Application with WebRTC Audio/Video Calling
class DockTalkApp {
  constructor() {
    this.socket = io()
    this.currentChat = null
    this.currentGroup = null
    this.currentCommunity = null
    this.messages = []
    this.isRecording = false
    this.recordingTime = 0
    this.recordingInterval = null
    this.mediaRecorder = null
    this.activeTab = "chats"
    this.searchQuery = ""
    this.isMobile = window.innerWidth < 768

    // WebRTC properties
    this.callState = {
      isActive: false,
      callId: null,
      type: null,
      contact: "",
      duration: 0,
      isConnected: false,
      isMuted: false,
      isVideoOff: false,
      isIncoming: false,
    }
    this.callInterval = null
    this.localStream = null
    this.remoteStream = null
    this.peerConnection = null
    this.audioElements = {}
    this.typingTimer = null
    this.isTyping = false
    this.currentModal = null

    // WebRTC configuration
    this.rtcConfiguration = {
      iceServers: [
        { urls: "stun:stun.l.google.com:19302" },
        { urls: "stun:stun1.l.google.com:19302" },
        { urls: "stun:stun2.l.google.com:19302" },
      ],
    }

    this.initializeSocketListeners()
    this.initializeEventListeners()
    this.initializeUI()
    this.checkMobile()
  }

  initializeSocketListeners() {
    this.socket.on("connect", () => {
      console.log("Connected to server")
    })

    this.socket.on("disconnect", () => {
      console.log("Disconnected from server")
    })

    this.socket.on("new_message", (data) => {
      this.handleNewMessage(data)
    })

    this.socket.on("user_status", (data) => {
      this.updateUserStatus(data.user_id, data.status)
    })

    this.socket.on("user_typing", (data) => {
      this.showTypingIndicator(data)
    })

    this.socket.on("user_stop_typing", (data) => {
      this.hideTypingIndicator(data)
    })

    // WebRTC call event listeners
    this.socket.on("incoming_call", (data) => {
      this.handleIncomingCall(data)
    })

    this.socket.on("call_answered", (data) => {
      this.handleCallAnswered(data)
    })

    this.socket.on("call_ended", (data) => {
      this.handleCallEnded(data)
    })

    this.socket.on("join_call_room", (data) => {
      this.socket.emit("join_call_room", { call_id: data.call_id })
    })

    this.socket.on("webrtc_offer", async (data) => {
      await this.handleWebRTCOffer(data)
    })

    this.socket.on("webrtc_answer", async (data) => {
      await this.handleWebRTCAnswer(data)
    })

    this.socket.on("webrtc_ice_candidate", async (data) => {
      await this.handleWebRTCIceCandidate(data)
    })

    this.socket.on("call_error", (data) => {
      this.showNotification(data.message, "error")
      this.endCall()
    })

    this.socket.on("message_status_update", (data) => {
      const { message_id, status } = data;
      const msgElement = document.querySelector(`[data-message-id="${message_id}"]`);
      if (msgElement) {
        const statusSpan = msgElement.querySelector(".message-status");
        if (statusSpan) statusSpan.innerHTML = getStatusIcon(status);
      }
    });

  }

  initializeEventListeners() {
    // Mobile menu
    document.getElementById("mobileMenuBtn").addEventListener("click", () => {
      this.toggleMobileSidebar()
    })

    document.getElementById("backBtn").addEventListener("click", () => {
      this.toggleMobileSidebar()
    })

    // Close mobile sidebar when clicking overlay
    document.getElementById("mobileSidebarOverlay").addEventListener("click", (e) => {
      if (e.target === e.currentTarget) {
        this.toggleMobileSidebar()
      }
    })

    // Close modal when clicking overlay
    document.getElementById("modalOverlay").addEventListener("click", (e) => {
      if (e.target === e.currentTarget) {
        this.closeModal()
      }
    })

    // Message input
    const messageInput = document.getElementById("messageInput")
    messageInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault()
        this.sendMessage()
      }
    })

    messageInput.addEventListener("input", () => {
      this.handleTyping()
    })

    // Auto-resize textarea
    messageInput.addEventListener("input", function () {
      this.style.height = "auto"
      this.style.height = Math.min(this.scrollHeight, 120) + "px"
    })

    // Buttons
    document.getElementById("sendBtn").addEventListener("click", () => this.sendMessage())
    document.getElementById("voiceBtn").addEventListener("click", () => this.toggleVoiceRecording())
    document.getElementById("attachBtn").addEventListener("click", () => this.handleFileUpload("file"))
    document.getElementById("imageBtn").addEventListener("click", () => this.handleFileUpload("image"))
    document.getElementById("audioCallBtn").addEventListener("click", () => this.startCall("audio"))
    document.getElementById("videoCallBtn").addEventListener("click", () => this.startCall("video"))
    document.getElementById("announcementBtn").addEventListener("click", () => this.showAnnouncementPanel())
    document.getElementById("infoBtn").addEventListener("click", () => this.showInfoPanel())

    // Call controls
    document.getElementById("muteBtn").addEventListener("click", () => this.toggleMute())
    document.getElementById("videoBtn").addEventListener("click", () => this.toggleVideo())
    document.getElementById("endCallBtn").addEventListener("click", () => this.endCall())

    // File inputs
    document.getElementById("fileInput").addEventListener("change", (e) => this.onFileSelect(e, "file"))
    document.getElementById("imageInput").addEventListener("change", (e) => this.onFileSelect(e, "image"))

    // User search in modal
    document.getElementById("userSearch").addEventListener("input", (e) => {
      this.searchUsers(e.target.value)
    })

    // Window resize
    window.addEventListener("resize", () => this.checkMobile())
  }

  async initializeUI() {
    await this.loadChatData()
    this.renderChatList()
    this.showWelcomeScreen()
  }

  async loadChatData() {
    try {
      // Load individual chats
      const chatsResponse = await fetch("/api/chats")
      this.chats = await chatsResponse.json()

      // Load groups
      const groupsResponse = await fetch("/api/groups")
      this.groups = await groupsResponse.json()

      // Load communities
      const communitiesResponse = await fetch("/api/communities")
      this.communities = await communitiesResponse.json()

      this.expandedCommunities = this.communities.map((c) => c.id)
    } catch (error) {
      console.error("Error loading chat data:", error)
      this.chats = []
      this.groups = []
      this.communities = []
      this.expandedCommunities = []
    }
  }

  // WebRTC Call Methods
  async startCall(type) {
    const entity = this.currentChat || this.currentGroup
    if (!entity) return

    try {
      // Get user media
      const constraints = {
        audio: true,
        video: type === "video",
      }

      this.localStream = await navigator.mediaDevices.getUserMedia(constraints)

      // Show call interface
      this.showCallInterface(type, entity)

      // Set up local video if video call
      if (type === "video") {
        const localVideo = document.getElementById("localVideo")
        localVideo.srcObject = this.localStream
        document.getElementById("localVideoContainer").classList.remove("hidden")
      }

      // Create peer connection
      this.createPeerConnection()

      // Add local stream to peer connection
      this.localStream.getTracks().forEach((track) => {
        this.peerConnection.addTrack(track, this.localStream)
      })

      // Emit start call event
      this.socket.emit("start_call", {
        type: type,
        target_type: this.currentChat ? "user" : "group",
        target_id: entity.id,
      })

      this.callState.isActive = true
      this.callState.type = type
      this.callState.contact = entity.name
      this.startCallTimer()
    } catch (error) {
      console.error("Error starting call:", error)
      this.showNotification("Could not access camera/microphone. Please check permissions.", "error")
      this.endCall()
    }
  }

  createPeerConnection() {
    this.peerConnection = new RTCPeerConnection(this.rtcConfiguration)

    // Handle remote stream
    this.peerConnection.ontrack = (event) => {
      console.log("Received remote stream")
      this.remoteStream = event.streams[0]

      if (this.callState.type === "video") {
        const remoteVideo = document.querySelector("#remoteVideo video")
        remoteVideo.srcObject = this.remoteStream
        document.getElementById("remoteVideo").classList.remove("hidden")
        document.getElementById("audioCallDisplay").classList.add("hidden")
      }
    }

    // Handle ICE candidates
    this.peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        this.socket.emit("webrtc_ice_candidate", {
          call_id: this.callState.callId,
          candidate: event.candidate,
          target_id: this.currentChat ? this.currentChat.id : null,
        })
      }
    }

    // Handle connection state changes
    this.peerConnection.onconnectionstatechange = () => {
      console.log("Connection state:", this.peerConnection.connectionState)
      if (this.peerConnection.connectionState === "connected") {
        this.callState.isConnected = true
        document.getElementById("callStatus").textContent = "Connected"
      } else if (
        this.peerConnection.connectionState === "disconnected" ||
        this.peerConnection.connectionState === "failed"
      ) {
        this.endCall()
      }
    }
  }

  async handleIncomingCall(data) {
    this.callState.callId = data.call_id
    this.callState.isIncoming = true
    this.callState.type = data.type

    const acceptCall = confirm(`Incoming ${data.type} call from ${data.caller.name}. Accept?`)

    if (acceptCall) {
      try {
        // Get user media
        const constraints = {
          audio: true,
          video: data.type === "video",
        }

        this.localStream = await navigator.mediaDevices.getUserMedia(constraints)

        // Show call interface
        this.showCallInterface(data.type, { name: data.caller.name, avatar: data.caller.avatar })

        // Set up local video if video call
        if (data.type === "video") {
          const localVideo = document.getElementById("localVideo")
          localVideo.srcObject = this.localStream
          document.getElementById("localVideoContainer").classList.remove("hidden")
        }

        // Create peer connection
        this.createPeerConnection()

        // Add local stream to peer connection
        this.localStream.getTracks().forEach((track) => {
          this.peerConnection.addTrack(track, this.localStream)
        })

        // Answer the call
        this.socket.emit("answer_call", {
          call_id: data.call_id,
        })

        this.callState.isActive = true
        this.callState.contact = data.caller.name
        this.startCallTimer()
      } catch (error) {
        console.error("Error answering call:", error)
        this.showNotification("Could not access camera/microphone. Please check permissions.", "error")
        this.socket.emit("end_call", { call_id: data.call_id })
      }
    } else {
      // Decline the call
      this.socket.emit("end_call", { call_id: data.call_id })
    }
  }

  async handleCallAnswered(data) {
    this.callState.callId = data.call_id
    console.log("Call answered by:", data.answerer.name)

    // Create and send offer
    try {
      const offer = await this.peerConnection.createOffer()
      await this.peerConnection.setLocalDescription(offer)

      this.socket.emit("webrtc_offer", {
        call_id: this.callState.callId,
        offer: offer,
        target_id: this.currentChat ? this.currentChat.id : null,
      })
    } catch (error) {
      console.error("Error creating offer:", error)
      this.endCall()
    }
  }

  async handleWebRTCOffer(data) {
    if (data.call_id !== this.callState.callId) return

    try {
      await this.peerConnection.setRemoteDescription(data.offer)

      const answer = await this.peerConnection.createAnswer()
      await this.peerConnection.setLocalDescription(answer)

      this.socket.emit("webrtc_answer", {
        call_id: this.callState.callId,
        answer: answer,
        target_id: data.from_user_id,
      })
    } catch (error) {
      console.error("Error handling offer:", error)
      this.endCall()
    }
  }

  async handleWebRTCAnswer(data) {
    if (data.call_id !== this.callState.callId) return

    try {
      await this.peerConnection.setRemoteDescription(data.answer)
    } catch (error) {
      console.error("Error handling answer:", error)
      this.endCall()
    }
  }

  async handleWebRTCIceCandidate(data) {
    if (data.call_id !== this.callState.callId) return

    try {
      await this.peerConnection.addIceCandidate(data.candidate)
    } catch (error) {
      console.error("Error adding ICE candidate:", error)
    }
  }

  handleCallEnded(data) {
    console.log("Call ended")
    this.endCall()
  }

  showCallInterface(type, entity) {
    const callInterface = document.getElementById("callInterface")
    const callContactName = document.getElementById("callContactName")
    const callContactAvatar = document.getElementById("callContactAvatar")

    callContactName.textContent = entity.name
    callContactAvatar.src = entity.avatar || "/static/default-avatar.png"

    if (type === "video") {
      document.getElementById("remoteVideo").classList.remove("hidden")
      document.getElementById("audioCallDisplay").classList.add("hidden")
      document.getElementById("videoBtn").classList.remove("hidden")
    } else {
      document.getElementById("remoteVideo").classList.add("hidden")
      document.getElementById("audioCallDisplay").classList.remove("hidden")
      document.getElementById("videoBtn").classList.add("hidden")
    }

    callInterface.classList.remove("hidden")
    document.getElementById("callStatus").textContent = this.callState.isIncoming ? "Connecting..." : "Calling..."
  }

  startCallTimer() {
    this.callState.duration = 0
    this.callInterval = setInterval(() => {
      this.callState.duration++
      const minutes = Math.floor(this.callState.duration / 60)
      const seconds = this.callState.duration % 60
      const timeString = `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`

      const statusOverlay = document.getElementById("callStatusOverlay")
      if (statusOverlay && this.callState.isConnected) {
        statusOverlay.textContent = timeString
        statusOverlay.classList.remove("hidden")
      }
    }, 1000)
  }

  toggleMute() {
    if (this.localStream) {
      const audioTrack = this.localStream.getAudioTracks()[0]
      if (audioTrack) {
        audioTrack.enabled = !audioTrack.enabled
        this.callState.isMuted = !audioTrack.enabled

        const muteBtn = document.getElementById("muteBtn")
        const icon = muteBtn.querySelector("i")

        if (this.callState.isMuted) {
          icon.className = "fas fa-microphone-slash"
          muteBtn.style.background = "#ef4444"
        } else {
          icon.className = "fas fa-microphone"
          muteBtn.style.background = "rgba(255, 255, 255, 0.2)"
        }
      }
    }
  }

  toggleVideo() {
    if (this.localStream && this.callState.type === "video") {
      const videoTrack = this.localStream.getVideoTracks()[0]
      if (videoTrack) {
        videoTrack.enabled = !videoTrack.enabled
        this.callState.isVideoOff = !videoTrack.enabled

        const videoBtn = document.getElementById("videoBtn")
        const icon = videoBtn.querySelector("i")

        if (this.callState.isVideoOff) {
          icon.className = "fas fa-video-slash"
          videoBtn.style.background = "#ef4444"
        } else {
          icon.className = "fas fa-video"
          videoBtn.style.background = "rgba(255, 255, 255, 0.2)"
        }
      }
    }
  }

  endCall() {
    // Emit end call event
    if (this.callState.callId) {
      this.socket.emit("end_call", {
        call_id: this.callState.callId,
      })
    }

    // Stop local stream
    if (this.localStream) {
      this.localStream.getTracks().forEach((track) => track.stop())
      this.localStream = null
    }

    // Close peer connection
    if (this.peerConnection) {
      this.peerConnection.close()
      this.peerConnection = null
    }

    // Clear call timer
    if (this.callInterval) {
      clearInterval(this.callInterval)
      this.callInterval = null
    }

    // Reset call state
    this.callState = {
      isActive: false,
      callId: null,
      type: null,
      contact: "",
      duration: 0,
      isConnected: false,
      isMuted: false,
      isVideoOff: false,
      isIncoming: false,
    }

    // Hide call interface
    document.getElementById("callInterface").classList.add("hidden")
    document.getElementById("localVideoContainer").classList.add("hidden")
    document.getElementById("videoBtn").classList.add("hidden")

    // Reset button states
    const muteBtn = document.getElementById("muteBtn")
    const videoBtn = document.getElementById("videoBtn")
    muteBtn.querySelector("i").className = "fas fa-microphone"
    videoBtn.querySelector("i").className = "fas fa-video"
    muteBtn.style.background = "rgba(255, 255, 255, 0.2)"
    videoBtn.style.background = "rgba(255, 255, 255, 0.2)"
  }

  // Modal Management
  showModal(modalId) {
    this.closeModal() // Close any existing modal
    this.currentModal = modalId
    document.getElementById("modalOverlay").classList.remove("hidden")
    document.getElementById(modalId).classList.remove("hidden")
    document.body.style.overflow = "hidden"
  }

  closeModal() {
    if (this.currentModal) {
      document.getElementById(this.currentModal).classList.add("hidden")
      this.currentModal = null
    }
    document.getElementById("modalOverlay").classList.add("hidden")
    document.body.style.overflow = "";

    const dynamicModal = document.getElementById("dynamicModal");
    if (dynamicModal) dynamicModal.remove(); // only remove dynamic one
}

  showActionsModal() {
    this.showModal("actionsModal")
  }

  showCreateCommunityModal() {
    this.closeModal()
    this.showModal("createCommunityModal")
  }

  showCreateGroupModal() {
    this.closeModal()
    if (!this.communities || this.communities.length === 0) {
      this.showNotification("You must be a member of a community to create groups", "error")
      return
    }

    // Populate community dropdown
    const select = document.getElementById("groupCommunity")
    select.innerHTML = '<option value="">Select a community...</option>'
    this.communities.forEach((community) => {
      const option = document.createElement("option")
      option.value = community.id
      option.textContent = community.name
      select.appendChild(option)
    })

    this.showModal("createGroupModal")
  }

  showStartChatModal() {
    this.closeModal()
    document.getElementById("userSearch").value = ""
    document.getElementById("userSearchResults").innerHTML = ""
    this.showModal("startChatModal")
  }

  async showJoinCommunityModal() {
    this.closeModal()
    try {
      const response = await fetch("/api/communities/all")
      const communities = await response.json()

      const availableCommunities = communities.filter((c) => !c.is_member)
      const container = document.getElementById("availableCommunities")

      if (availableCommunities.length === 0) {
        container.innerHTML = '<p class="text-center text-gray-500">No communities available to join</p>'
      } else {
        container.innerHTML = availableCommunities
          .map(
            (community) => `
          <div class="community-result">
            <div class="result-avatar">${community.name[0]}</div>
            <div class="result-info">
              <div class="result-name">${community.name}</div>
              <div class="result-details">${community.description}</div>
              <div class="result-details">${community.members} members</div>
            </div>
            <button class="result-action" onclick="app.joinCommunity('${community.id}')">Join</button>
          </div>
        `,
          )
          .join("")
      }

      this.showModal("joinCommunityModal")
    } catch (error) {
      this.showNotification("Failed to load communities", "error")
    }
  }

  async showJoinGroupModal() {
    this.closeModal()
    try {
      const response = await fetch("/api/groups/all")
      const groups = await response.json()

      const availableGroups = groups.filter((g) => !g.is_member)
      const container = document.getElementById("availableGroups")

      if (availableGroups.length === 0) {
        container.innerHTML = '<p class="text-center text-gray-500">No groups available to join</p>'
      } else {
        container.innerHTML = availableGroups
          .map(
            (group) => `
          <div class="group-result">
            <div class="result-avatar"><i class="fas fa-users"></i></div>
            <div class="result-info">
              <div class="result-name">${group.name}</div>
              <div class="result-details">${group.description}</div>
              <div class="result-details">${group.community.name} • ${group.members} members</div>
            </div>
            <button class="result-action" onclick="app.joinGroup('${group.id}')">Join</button>
          </div>
        `,
          )
          .join("")
      }

      this.showModal("joinGroupModal")
    } catch (error) {
      this.showNotification("Failed to load groups", "error")
    }
  }

  // Action Methods
  async createCommunity() {
    const name = document.getElementById("communityName").value.trim()
    const description = document.getElementById("communityDescription").value.trim()

    if (!name) {
      this.showNotification("Community name is required", "error")
      return
    }

    try {
      const response = await fetch("/api/create_community", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description }),
      })

      const result = await response.json()
      if (result.success) {
        this.showNotification("Community created successfully!", "success")
        this.closeModal()
        await this.loadChatData()
        this.renderChatList()
      } else {
        this.showNotification("Error: " + result.error, "error")
      }
    } catch (error) {
      this.showNotification("Failed to create community", "error")
    }
  }

  async createGroup() {
    const name = document.getElementById("groupName").value.trim()
    const description = document.getElementById("groupDescription").value.trim()
    const communityId = document.getElementById("groupCommunity").value
    const expiresAt = document.getElementById("groupExpiry").value

    if (!name || !communityId) {
      this.showNotification("Group name and community are required", "error")
      return
    }

    try {
      const response = await fetch("/api/create_group", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description,
          community_id: communityId,
          expires_at: expiresAt || null,
        }),
      })

      const result = await response.json()
      if (result.success) {
        this.showNotification("Group created successfully!", "success")
        this.closeModal()
        await this.loadChatData()
        this.renderChatList()
      } else {
        this.showNotification("Error: " + result.error, "error")
      }
    } catch (error) {
      this.showNotification("Failed to create group", "error")
    }
  }

  async joinCommunity(communityId) {
    try {
      const response = await fetch("/api/join_community", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ community_id: communityId }),
      })

      const result = await response.json()
      if (result.success) {
        this.showNotification("Successfully joined community!", "success")
        this.closeModal()
        await this.loadChatData()
        this.renderChatList()
      } else {
        this.showNotification("Error: " + result.error, "error")
      }
    } catch (error) {
      this.showNotification("Failed to join community", "error")
    }
  }

  async joinGroup(groupId) {
    try {
      const response = await fetch("/api/join_group", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group_id: groupId }),
      })

      const result = await response.json()
      if (result.success) {
        this.showNotification("Successfully joined group!", "success")
        this.closeModal()
        await this.loadChatData()
        this.renderChatList()
      } else {
        this.showNotification("Error: " + result.error, "error")
      }
    } catch (error) {
      this.showNotification("Failed to join group", "error")
    }
  }

  async searchUsers(query) {
    if (!query.trim()) {
      document.getElementById("userSearchResults").innerHTML = ""
      return
    }

    try {
      const response = await fetch(`/api/users/search?q=${encodeURIComponent(query)}`)
      const users = await response.json()

      const container = document.getElementById("userSearchResults")
      if (users.length === 0) {
        container.innerHTML = '<p class="text-center text-gray-500">No users found</p>'
      } else {
        container.innerHTML = users
          .map(
            (user) => `
          <div class="user-result" onclick="app.startChatWithUser('${user.id}')">
            <div class="result-avatar">${user.full_name[0]}</div>
            <div class="result-info">
              <div class="result-name">${user.full_name}</div>
              <div class="result-details">@${user.username} • ${user.department || "No department"}</div>
              <div class="result-details">${user.location || ""}</div>
            </div>
            <button class="result-action">Chat</button>
          </div>
        `,
          )
          .join("")
      }
    } catch (error) {
      this.showNotification("Failed to search users", "error")
    }
  }
  
  async startChatWithUser(userId) {
    try {
      const response = await fetch("/api/start_chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId }),
      })

      const result = await response.json()
      if (result.success) {
        this.chats = this.chats || []
        this.chats.unshift(result.chat)
        this.selectChat(result.chat.id)
        this.renderChatList()
        this.closeModal()
      } else {
        this.showNotification("Error: " + result.error, "error")
      }
    } catch (error) {
      this.showNotification("Failed to start chat", "error")
    }
  }

  showNotification(message, type = "info") {
    // Create notification element
    const notification = document.createElement("div")
    notification.className = `notification notification-${type}`
    notification.innerHTML = `
      <div class="notification-content">
        <i class="fas fa-${type === "success" ? "check-circle" : type === "error" ? "exclamation-circle" : "info-circle"}"></i>
        <span>${message}</span>
      </div>
    `

    // Add to page
    document.body.appendChild(notification)

    // Remove after 3 seconds
    setTimeout(() => {
      notification.remove()
    }, 3000)
  }

  handleNewMessage(data)
{
  // Add message to current chat if it matches
  if (
    (this.currentChat &&
      data.chat_type === "user" &&
      (data.chat_id == this.currentChat.id || data.sender.id == this.currentChat.id)) ||
    (this.currentGroup && data.chat_type === "group" && data.chat_id == this.currentGroup.id)
  ) {
    // Check if this message was just sent by the current user
    // If it's from the current user and matches the last message in our array, don't add it again
    const isOwnMessage = data.sender.id == window.currentUser.id
    const isDuplicate = this.messages.some(
      (msg) =>
        msg.id === data.id ||
        (isOwnMessage && msg.content === data.content && new Date(msg.timestamp).getTime() > Date.now() - 2000),
    )

    if (!isDuplicate) {
      const message = {
        id: data.id,
        type: data.type,
        content: data.content,
        sender: data.sender.id == window.currentUser.id ? "You" : data.sender.name,
        timestamp: new Date(data.timestamp),
        isAnnouncement: data.is_announcement,
        fileData: data.file_data,
      }

      this.messages.push(message)
      this.renderMessages()
      this.scrollToBottom()
    }
  }

  // Update chat list
  this.loadChatData().then(() => {
    this.renderChatList()
  })
}


  updateUserStatus(userId, status) {
    // Update online status in UI
    const indicators = document.querySelectorAll(`[data-user-id="${userId}"] .online-indicator`)
    indicators.forEach((indicator) => {
      if (status === "online") {
        indicator.classList.remove("hidden")
      } else {
        indicator.classList.add("hidden")
      }
    })
  }

  handleTyping() {
    if (!this.currentChat && !this.currentGroup) return

    if (!this.isTyping) {
      this.isTyping = true
      this.socket.emit("typing_start", {
        chat_type: this.currentChat ? "user" : "group",
        chat_id: this.currentChat ? this.currentChat.id : this.currentGroup.id,
      })
    }

    clearTimeout(this.typingTimer)
    this.typingTimer = setTimeout(() => {
      this.isTyping = false
      this.socket.emit("typing_stop", {
        chat_type: this.currentChat ? "user" : "group",
        chat_id: this.currentChat ? this.currentChat.id : this.currentGroup.id,
      })
    }, 1000)
  }

  showTypingIndicator(data) {
    if (data.user.id === window.currentUser.id) return

    const indicator = document.getElementById("typingIndicator")
    const text = document.getElementById("typingText")
    text.textContent = ``
    indicator.classList.remove("hidden")
  }

  hideTypingIndicator(data) {
    if (data.user.id === window.currentUser.id) return

    const indicator = document.getElementById("typingIndicator")
    indicator.classList.add("hidden")
  }

  checkMobile() {
    const wasMobile = this.isMobile
    this.isMobile = window.innerWidth < 768

    if (wasMobile !== this.isMobile) {
      if (!this.isMobile) {
        this.hideMobileSidebar()
      }
    }
  }

  toggleMobileSidebar() {
    const overlay = document.getElementById("mobileSidebarOverlay")
    overlay.classList.toggle("hidden")
  }

  hideMobileSidebar() {
    const overlay = document.getElementById("mobileSidebarOverlay")
    overlay.classList.add("hidden")
  }

  renderChatList() {
    const chatListHTML = this.generateChatListHTML()
    document.getElementById("chatList").innerHTML = chatListHTML
    document.getElementById("mobileChatList").innerHTML = chatListHTML
    this.attachChatListEventListeners()
  }

  generateChatListHTML() {
    return `
    <div class="chat-list-header">
      <div class="header-top">
        <div class="app-title">
        <img src="static/nimasa.png" style="width:30px">
          <h1>StaffComm</h1>
        </div>
        <div class="header-actions">
          <button class="header-btn" onclick="app.showActionsModal()" title="Actions">
            <i class="fas fa-plus"></i>
          </button>
          <a href="/logout" class="header-btn" title="Logout">
            <i class="fas fa-sign-out-alt"></i>
          </a>
        </div>
      </div>
      <div class="app-subtitle">NIMASA Maritime Communication</div>
      <div class="search-container">
        <i class="fas fa-search search-icon"></i>
        <input type="text" class="search-input" placeholder="Search contacts, groups..." value="${this.searchQuery}">
      </div>
    </div>
    <div class="tabs-container">
      <div class="tabs-list">
        <button class="tab-trigger ${this.activeTab === "chats" ? "active" : ""}" data-tab="chats">Chats</button>
        <button class="tab-trigger ${this.activeTab === "groups" ? "active" : ""}" data-tab="groups">Groups</button>
        <button class="tab-trigger ${this.activeTab === "communities" ? "active" : ""}" data-tab="communities">Communities</button>
      </div>
    </div>
    <div class="chat-items">
      ${this.renderTabContent()}
    </div>
  `
  }

  renderTabContent() {
    switch (this.activeTab) {
      case "chats":
        return this.renderIndividualChats()
      case "groups":
        return this.renderGroups()
      case "communities":
        return this.renderCommunities()
      default:
        return ""
    }
  }

  renderIndividualChats() {
    if (!this.chats || this.chats.length === 0) {
      return '<div class="empty-state">No chats yet. Start a conversation!</div>'
    }

    const filteredChats = this.chats.filter(
      (chat) =>
        chat.name.toLowerCase().includes(this.searchQuery.toLowerCase()) ||
        chat.lastMessage.toLowerCase().includes(this.searchQuery.toLowerCase()) ||
        (chat.department && chat.department.toLowerCase().includes(this.searchQuery.toLowerCase())),
    )

    return filteredChats
      .map(
        (chat) => `
      <div class="chat-item ${this.currentChat?.id == chat.id ? "active" : ""}" data-chat-id="${chat.id}">
        <div class="chat-avatar-container" data-user-id="${chat.id}">
          <div class="contact-avatar">
            <img src="${chat.avatar}" alt="${chat.name}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
            <div class="contact-initial" style="display: none;">${chat.name[0]}</div>
            ${chat.isOnline ? '<div class="online-indicator"></div>' : ""}
          </div>
        </div>
        <div class="chat-info">
          <div class="chat-header-info">
            <h3 class="chat-name">${chat.name}</h3>
            <span class="chat-time">${this.formatTime(new Date(new Date(chat.timestamp).getTime() + 60 * 60 * 1000))}</span>
          </div>
          <p class="chat-message">${chat.lastMessage}</p>
          <p class="chat-department">${chat.department || ""}</p>
        </div>
        ${chat.unread > 0 ? `<div class="unread-badge">${chat.unread}</div>` : ""}
      </div>

    `,
      )
      .join("")
  }

  renderGroups() {
    if (!this.groups || this.groups.length === 0) {
      return '<div class="empty-state">No groups yet. Join a community to access groups!</div>'
    }

    const filteredGroups = this.groups.filter(
      (group) =>
        group.name.toLowerCase().includes(this.searchQuery.toLowerCase()) ||
        group.lastMessage.toLowerCase().includes(this.searchQuery.toLowerCase()),
    )

    return filteredGroups
      .map(
        (group) => `
      <div class="chat-item ${this.currentGroup?.id == group.id ? "active" : ""}" data-group-id="${group.id}" data-community-id="${group.community.id}">
        <div class="chat-avatar-container">
          <div class="contact-avatar">
            <img src="${group.avatar}" alt="${group.name}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
            <div class="contact-initial" style="display: none;"><i class="fas fa-users"></i></div>
          </div>
        </div>
        <div class="chat-info">
          <div class="chat-header-info">
            <h3 class="chat-name">${group.name}</h3>
            <span class="chat-time">${this.formatTime(new Date(group.timestamp))}</span>
          </div>
          <p class="chat-message">${group.lastMessage}</p>
          <div class="chat-header-info">
            <span class="chat-members">${group.members} members</span>
            <span class="chat-department">${group.community.name}</span>
          </div>
        </div>
        ${group.unread > 0 ? `<div class="unread-badge">${group.unread}</div>` : ""}
      </div>
    `,
      )
      .join("")
  }

  renderCommunities() {
    if (!this.communities || this.communities.length === 0) {
      return '<div class="empty-state">No communities available.</div>'
    }

    return this.communities
      .map(
        (community) => `
      <div class="community-item">
        <div class="community-header" data-community-id="${community.id}">
          <div class="contact-avatar">
            <img src="${community.avatar}" alt="${community.name}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
            <div class="contact-initial" style="display: none;"><i class="fas fa-globe"></i></div>
          </div>
          <div class="community-info">
            <div class="chat-header-info">
              <h3 class="chat-name">${community.name}</h3>
              <div class="community-actions">
                <button class="header-btn announcement-btn" data-community-id="${community.id}">
                  <i class="fas fa-bullhorn"></i>
                </button>
                <i class="fas fa-chevron-right expand-icon ${this.expandedCommunities.includes(community.id) ? "expanded" : ""}"></i>
              </div>
            </div>
            <p class="chat-message">${community.description}</p>
            <span class="chat-members">${community.members.toLocaleString()} members</span>
          </div>
        </div>
        <div class="community-groups ${this.expandedCommunities.includes(community.id) ? "" : "hidden"}">
          ${community.groups
            .map(
              (group) => `
            <div class="group-item ${this.currentGroup?.id == group.id ? "active" : ""}" data-group-id="${group.id}" data-community-id="${community.id}">
              <div class="contact-avatar group-avatar">
                <img src="${group.avatar}" alt="${group.name}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                <div class="contact-initial" style="display: none;"><i class="fas fa-users"></i></div>
              </div>
              <div class="group-info">
                <div class="chat-header-info">
                  <h4 class="group-name">${group.name}</h4>
                  <span class="chat-time">${this.formatTime(new Date(group.timestamp))}</span>
                </div>
                <p class="group-message">${group.lastMessage}</p>
                <div class="group-meta">
                  <span class="chat-members">${group.members} members</span>
                  ${
                    group.expiresAt
                      ? `
                    <div class="expiry-info">
                      <i class="fas fa-clock"></i>
                      <span>${this.formatExpiry(new Date(group.expiresAt))}</span>
                    </div>
                  `
                      : ""
                  }
                </div>
              </div>
              ${group.unread > 0 ? `<div class="unread-badge">${group.unread}</div>` : ""}
            </div>
          `,
            )
            .join("")}
        </div>
      </div>
    `,
      )
      .join("")
  }

  attachChatListEventListeners() {
    // Tab switching
    document.querySelectorAll(".tab-trigger").forEach((tab) => {
      tab.addEventListener("click", (e) => {
        this.activeTab = e.target.dataset.tab
        this.renderChatList()
      })
    })

    // Search input
    const searchInput = document.querySelector(".search-input")
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        this.searchQuery = e.target.value
        const cursorPosition = e.target.selectionStart
        this.renderChatList()
        setTimeout(() => {
          const newSearchInput = document.querySelector(".search-input")
          if (newSearchInput) {
            newSearchInput.focus()
            newSearchInput.setSelectionRange(cursorPosition, cursorPosition)
          }
        }, 0)
      })
    }

    // Individual chat selection
    document.querySelectorAll(".chat-item[data-chat-id]").forEach((item) => {
      item.addEventListener("click", (e) => {
        const chatId = e.currentTarget.dataset.chatId
        this.selectChat(chatId)
      })
    })

    // Group selection
    document.querySelectorAll(".chat-item[data-group-id], .group-item[data-group-id]").forEach((item) => {
      item.addEventListener("click", (e) => {
        const groupId = e.currentTarget.dataset.groupId
        const communityId = e.currentTarget.dataset.communityId
        this.selectGroup(communityId, groupId)
      })
    })

    // Community expansion
    document.querySelectorAll(".community-header").forEach((header) => {
      header.addEventListener("click", (e) => {
        if (e.target.closest(".announcement-btn")) return
        const communityId = e.currentTarget.dataset.communityId
        this.toggleCommunityExpansion(communityId)
      })
    })

    // Announcement buttons
    document.querySelectorAll(".announcement-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation()
        const communityId = e.currentTarget.dataset.communityId
        this.showAnnouncementPanel(communityId)
      })
    })
  }

  

  selectChat(chatId) {
    this.currentChat = this.chats.find((chat) => chat.id == chatId)
    this.currentGroup = null
    this.currentCommunity = null

    // Join chat room
    this.socket.emit("join_chat", {
      type: "user",
      id: chatId,
    })

    this.loadMessages()
    this.showChatInterface()
    if (this.isMobile) {
      this.hideMobileSidebar()
    }

    const seenMessages = document.querySelectorAll(".message[data-message-id]");
    seenMessages.forEach(msg => {
      const id = msg.dataset.messageId;
      this.socket.emit("message_seen", {
        message_id: id,
        user_id: window.currentUser.id
      });
    });

  }




  checkIfGroupExpired(groupId) {
    return fetch(`/api/group_status?group_id=${groupId}`)
      .then(res => res.json())
      .then(data => data.expired);
  }

  disableMessageInput() {
    const input = document.getElementById("messageInput");
    const sendBtn = document.getElementById("sendBtn");
    input.disabled = true;
    input.placeholder = "This group has expired.";
    sendBtn.disabled = true;
  }

  enableMessageInput() {
    const input = document.getElementById("messageInput");
    const sendBtn = document.getElementById("sendBtn");
    input.disabled = false;
    input.placeholder = "Type a message...";
    sendBtn.disabled = false;
  }

  selectGroup(communityId, groupId) {
    this.currentCommunity = this.communities.find((c) => c.id == communityId)
    this.currentGroup = this.currentCommunity?.groups.find((g) => g.id == groupId)
    this.currentChat = null

    // Join group room
    this.socket.emit("join_chat", {
      type: "group",
      id: groupId,
    })

    this.loadMessages()
    this.showChatInterface()
    if (this.isMobile) {
      this.hideMobileSidebar()
    }

    this.checkIfGroupExpired(group.id).then(expired => {
      if (expired) {
        this.disableMessageInput();
      } else {
        this.enableMessageInput();
      }
    });
  }

  toggleCommunityExpansion(communityId) {
    if (this.expandedCommunities.includes(communityId)) {
      this.expandedCommunities = this.expandedCommunities.filter((id) => id !== communityId)
    } else {
      this.expandedCommunities.push(communityId)
    }
    this.renderChatList()
  }

  async loadMessages() {
    const entity = this.currentChat || this.currentGroup
    if (!entity) return

    try {
      const chatType = this.currentChat ? "user" : "group"
      const chatId = entity.id

      const response = await fetch(`/api/messages?chat_type=${chatType}&chat_id=${chatId}`)
      const messagesData = await response.json()

      this.messages = messagesData.map((msg) => ({
        id: msg.id,
        type: msg.message_type,
        content: msg.content,
        sender: msg.sender_id == window.currentUser.id ? "You" : msg.sender_name,
        timestamp: new Date(msg.created_at),
        isAnnouncement: msg.is_announcement,
        fileData: {
          url: msg.file_url,
          name: msg.file_name,
          size: msg.file_size,
          duration: msg.voice_duration,
        },
      }))

      this.renderMessages()
    } catch (error) {
      console.error("Error loading messages:", error)
      this.messages = []
      this.renderMessages()
    }
  }

  showWelcomeScreen() {
    document.getElementById("welcomeScreen").classList.remove("hidden")
    document.getElementById("chatInterface").classList.add("hidden")
  }

  showChatInterface() {
    document.getElementById("welcomeScreen").classList.add("hidden")
    document.getElementById("chatInterface").classList.remove("hidden")
    this.updateChatHeader()
    this.renderMessages()
  }

  updateChatHeader() {
    const entity = this.currentChat || this.currentGroup
    if (!entity) return

    const chatAvatar = document.getElementById("chatAvatar")
    const chatInitial = document.getElementById("chatInitial")
    const chatName = document.getElementById("chatName")
    const chatStatus = document.getElementById("chatStatus")
    const onlineIndicator = document.getElementById("onlineIndicator")
    const communityInfo = document.getElementById("communityInfo")
    const audioCallBtn = document.getElementById("audioCallBtn")
    const videoCallBtn = document.getElementById("videoCallBtn")
    const announcementBtn = document.getElementById("announcementBtn")

    // Set avatar and name
    chatAvatar.src = entity.avatar
    chatAvatar.onerror = () => {
      chatAvatar.style.display = "none"
      chatInitial.style.display = "flex"
      chatInitial.textContent = entity.name[0]
    }
    chatName.textContent = entity.name

    // Set status and show/hide buttons based on chat type
    if (this.currentChat) {
      chatStatus.textContent = this.currentChat.isOnline ? "Online" : "Last seen recently"
      onlineIndicator.classList.toggle("hidden", !this.currentChat.isOnline)
      communityInfo.classList.add("hidden")
      audioCallBtn.classList.remove("hidden")
      videoCallBtn.classList.remove("hidden")
      announcementBtn.classList.add("hidden")
    } else if (this.currentGroup) {
      chatStatus.textContent = `${this.currentGroup.members} members`
      onlineIndicator.classList.add("hidden")
      if (this.currentCommunity) {
        communityInfo.textContent = `📢 ${this.currentCommunity.name}`
        communityInfo.classList.remove("hidden")
        announcementBtn.classList.remove("hidden")
      }
      audioCallBtn.classList.remove("hidden")
      videoCallBtn.classList.remove("hidden")
    }
  }

  renderMessages() {
  const messagesList = document.getElementById("messagesList")
  messagesList.innerHTML = this.messages
    .map((message) => {
      // Emit delivered if it's not from the current user
      if (message.sender_id !== window.currentUser.id) {
        this.socket.emit("message_delivered", {
          message_id: message.id,
          user_id: window.currentUser.id
        })
      }

      return this.renderMessage(message)
    })
    .join("")

  this.scrollToBottom()

  // Emit seen after rendering all
  const seenMessages = document.querySelectorAll(".message[data-message-id]")
  seenMessages.forEach((msg) => {
    const id = msg.dataset.messageId
    this.socket.emit("message_seen", {
      message_id: id,
      user_id: window.currentUser.id
    })
  })
}


  renderMessage(message) {
    if (message.isAnnouncement) {
      return `
        <div class="announcement-message">
          <div class="announcement-content">
            <div class="announcement-icon">
              <i class="fas fa-bullhorn"></i>
            </div>
            <div class="announcement-info">
              <div class="announcement-title">
                <span>📢 Community Announcement</span>
                <time>${this.formatMessageTime(message.timestamp)}</time>
              </div>
              <p class="announcement-sender">${message.sender}</p>
              <p class="announcement-text">${message.content}</p>
            </div>
          </div>
        </div>
      `
    }

    const isOwn = message.sender === "You"
    return `
      <div class="message ${isOwn ? "own" : ""}">
        <div class="message-content">
          ${!isOwn ? `<div class="message-sender">${message.sender}</div>` : ""}
          ${this.renderMessageContent(message)}
          <div class="message-time">${this.formatMessageTime(message.timestamp)}</div>
        </div>
      </div>
    `
  }

  renderMessageContent(message) {
    switch (message.type) {
      case "text":
        return `<div class="message-text">${message.content}</div>`
      case "voice":
        return `
          <div class="voice-message">
            <button class="voice-play-btn" onclick="app.playVoiceMessage('${message.id}', '${message.fileData.url}')">
              <i class="fas fa-play" id="voice-icon-${message.id}"></i>
            </button>
            <div class="voice-waveform">
              <div class="voice-progress" id="voice-progress-${message.id}"></div>
            </div>
            <span class="voice-duration">${message.fileData.duration || 0}s</span>
          </div>
        `
      case "image":
        return `
          <div class="image-message">
            <img src="${message.fileData.url}" alt="Shared image" onclick="window.open('${message.fileData.url}', '_blank')">
          </div>
        `
      case "file":
        return `
          <div class="file-message">
            <div class="file-icon">
              <i class="fas fa-paperclip"></i>
            </div>
            <div class="file-info">
              <div class="file-name">${message.fileData.name}</div>
              <div class="file-size">${message.fileData.size}</div>
            </div>
            <button class="file-download" onclick="app.downloadFile('${message.fileData.url}', '${message.fileData.name}')">
              <i class="fas fa-download"></i>
            </button>
          </div>
        `
      default:
        return `<div class="message-text">${message.content}</div>`
    }
  }

  scrollToBottom() {
    const messagesArea = document.getElementById("messagesArea")
    messagesArea.scrollTop = messagesArea.scrollHeight
  }

  sendMessage() {
    const messageInput = document.getElementById("messageInput")
    const content = messageInput.value.trim()
    if (!content) return

    const entity = this.currentChat || this.currentGroup
    if (!entity) return

    // Stop typing indicator
    if (this.isTyping) {
      this.isTyping = false
      clearTimeout(this.typingTimer)
      this.socket.emit("typing_stop", {
        chat_type: this.currentChat ? "user" : "group",
        chat_id: entity.id,
      })
    }

    // Send message via socket - don't add to UI immediately
    // The message will be displayed when we receive the 'new_message' event
    this.socket.emit("send_message", {
      content: content,
      chat_type: this.currentChat ? "user" : "group",
      chat_id: entity.id,
      message_type: "text",
    })

    messageInput.value = ""
    messageInput.style.height = "auto"

    messageElement.dataset.messageId = message.id;
    messageElement.innerHTML += `<span class="message-status">${getStatusIcon("sent")}</span>`;
  }

  async handleFileUpload(type) {
    const input = document.getElementById(type === "file" ? "fileInput" : "imageInput")
    input.click()
  }

  async onFileSelect(event, type) {
    const file = event.target.files?.[0]
    if (!file) return

    const entity = this.currentChat || this.currentGroup
    if (!entity) return

    // Upload file
    const formData = new FormData()
    formData.append("file", file)
    formData.append("type", type)

    try {
      const response = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      })

      const result = await response.json()

      if (result.success) {
        // Send file message via socket
        this.socket.emit("send_message", {
          content: result.file_name,
          chat_type: this.currentChat ? "user" : "group",
          chat_id: entity.id,
          message_type: result.file_type,
          file_data: {
            url: result.file_url,
            name: result.file_name,
            size: result.file_size,
          },
        })
      } else {
        this.showNotification("File upload failed: " + result.error, "error")
      }
    } catch (error) {
      console.error("Error uploading file:", error)
      this.showNotification("File upload failed", "error")
    }

    event.target.value = ""
  }

  async toggleVoiceRecording() {
    if (this.isRecording) {
      this.stopRecording()
    } else {
      this.startRecording()
    }
  }

  async startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 44100,
        },
      })

      // Try different formats for better compatibility
      let options = { mimeType: "audio/webm;codecs=opus" }
      if (!MediaRecorder.isTypeSupported(options.mimeType)) {
        options = { mimeType: "audio/webm" }
      }
      if (!MediaRecorder.isTypeSupported(options.mimeType)) {
        options = { mimeType: "audio/mp4" }
      }
      if (!MediaRecorder.isTypeSupported(options.mimeType)) {
        options = { mimeType: "audio/wav" }
      }

      this.mediaRecorder = new MediaRecorder(stream, options)
      this.audioChunks = []

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data)
        }
      }

      this.mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(this.audioChunks, { type: this.mediaRecorder.mimeType })

        // Upload voice message with proper filename
        const formData = new FormData()
        const extension = this.mediaRecorder.mimeType.includes("webm")
          ? "webm"
          : this.mediaRecorder.mimeType.includes("mp4")
            ? "mp4"
            : "wav"
        formData.append("file", audioBlob, `voice-message-${Date.now()}.${extension}`)
        formData.append("type", "voice")

        try {
          const response = await fetch("/api/upload", {
            method: "POST",
            body: formData,
          })

          const result = await response.json()

          if (result.success) {
            const entity = this.currentChat || this.currentGroup
            if (entity) {
              this.socket.emit("send_message", {
                content: "Voice message",
                chat_type: this.currentChat ? "user" : "group",
                chat_id: entity.id,
                message_type: "voice",
                file_data: {
                  url: result.file_url,
                  name: result.file_name,
                  size: result.file_size,
                  duration: this.recordingTime,
                },
              })
            }
          } else {
            this.showNotification("Failed to upload voice message: " + result.error, "error")
          }
        } catch (error) {
          console.error("Error uploading voice message:", error)
          this.showNotification("Failed to upload voice message", "error")
        }

        stream.getTracks().forEach((track) => track.stop())
      }

      this.mediaRecorder.start(100) // Collect data every 100ms
      this.isRecording = true
      this.recordingTime = 0

      // Update UI
      document.getElementById("voiceBtn").classList.add("recording")
      document.getElementById("voiceBtn").innerHTML = '<i class="fas fa-stop"></i>'
      document.getElementById("recordingIndicator").classList.remove("hidden")

      this.recordingInterval = setInterval(() => {
        this.recordingTime++
        document.getElementById("recordingTime").textContent = this.recordingTime
        const progress = (this.recordingTime / 60) * 100
        document.getElementById("recordingProgressBar").style.width = `${Math.min(progress, 100)}%`
      }, 1000)
    } catch (error) {
      console.error("Error accessing microphone:", error)
      this.showNotification("Could not access microphone. Please check permissions.", "error")
    }
  }

  stopRecording() {
    if (this.mediaRecorder && this.isRecording) {
      this.mediaRecorder.stop()
      this.isRecording = false

      if (this.recordingInterval) {
        clearInterval(this.recordingInterval)
      }

      // Update UI
      document.getElementById("voiceBtn").classList.remove("recording")
      document.getElementById("voiceBtn").innerHTML = '<i class="fas fa-microphone"></i>'
      document.getElementById("recordingIndicator").classList.add("hidden")
    }
  }

  playVoiceMessage(messageId, audioUrl) {
    if (!audioUrl) {
      this.showNotification("Audio file not found", "error")
      return
    }

    const playIcon = document.getElementById(`voice-icon-${messageId}`)
    const progressBar = document.getElementById(`voice-progress-${messageId}`)

    // Stop all other audio
    Object.values(this.audioElements).forEach((audio) => {
      audio.pause()
      audio.currentTime = 0
    })

    // Reset all play icons
    document.querySelectorAll('[id^="voice-icon-"]').forEach((icon) => {
      icon.className = "fas fa-play"
    })

    // Reset all progress bars
    document.querySelectorAll('[id^="voice-progress-"]').forEach((progress) => {
      progress.style.width = "0%"
    })

    if (this.audioElements[messageId]) {
      delete this.audioElements[messageId]
      return
    }

    const audio = new Audio()
    audio.crossOrigin = "anonymous"
    audio.preload = "auto"
    this.audioElements[messageId] = audio

    // Update play icon
    if (playIcon) playIcon.className = "fas fa-pause"

    audio.onloadstart = () => {
      console.log("Audio loading started")
    }

    audio.oncanplay = () => {
      console.log("Audio can start playing")
    }

    audio.onloadedmetadata = () => {
      console.log(`Audio duration: ${audio.duration}s`)
    }

    audio.ontimeupdate = () => {
      if (audio.duration && progressBar) {
        const progress = (audio.currentTime / audio.duration) * 100
        progressBar.style.width = `${progress}%`
      }
    }

    audio.onended = () => {
      delete this.audioElements[messageId]
      if (playIcon) playIcon.className = "fas fa-play"
      if (progressBar) progressBar.style.width = "0%"
    }

    audio.onerror = (e) => {
      console.error("Audio playback error:", e)
      console.error("Audio error details:", audio.error)
      this.showNotification("Failed to play voice message. File may be corrupted.", "error")
      delete this.audioElements[messageId]
      if (playIcon) playIcon.className = "fas fa-play"
      if (progressBar) progressBar.style.width = "0%"
    }

    // Set source and try to play
    audio.src = audioUrl
    audio.load()

    const playPromise = audio.play()
    if (playPromise !== undefined) {
      playPromise.catch((error) => {
        console.error("Audio play failed:", error)
        this.showNotification("Failed to play voice message. Try clicking again.", "error")
        delete this.audioElements[messageId]
        if (playIcon) playIcon.className = "fas fa-play"
      })
    }
  }

  downloadFile(url, fileName) {
    const link = document.createElement("a")
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  getStatusIcon(status) {
    if (status === "sent") return '<i class="fas fa-check"></i>';
    if (status === "delivered") return '<i class="fas fa-check-double"></i>';
    if (status === "seen") return '<i class="fas fa-check-double seen"></i>';
    return '';
  }



  showAddMemberModal(groupId) {
    const modal = document.getElementById("modalOverlay");
    modal.classList.remove("hidden");
    let dynamicModal = document.getElementById("dynamicModal");
      if (!dynamicModal) {
        dynamicModal = document.createElement("div");
        dynamicModal.id = "dynamicModal";
        dynamicModal.className = "modal";
        modal.appendChild(dynamicModal);
      }
      dynamicModal.innerHTML = `
            <div class="modal" style=" padding:10px; ">
        <h3>Add Member</h3>
        <input type="text" id="addMemberUsername" class="form-input" placeholder="Enter username">
        <div class="modal-footer">
          <button class="btn-secondary" onclick="app.closeModal()">Cancel</button>
          <button class="btn-primary" onclick="app.submitAddMember('${groupId}')">Add</button>
        </div>
      </div>`; // put your custom modal content here
  }

  submitAddMember(groupId) {
    const username = document.getElementById("addMemberUsername").value.trim();
    if (!username) return this.showNotification("Username is required", "error");

    fetch(`/api/lookup_user?username=${username}`)
      .then(res => res.json())
      .then(user => {
        if (user && user.id) {
          fetch("/api/add_member", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ group_id: groupId, user_id: user.id })
          }).then(() => {
            this.showNotification("User added", "success");
            this.closeModal();
          });
        } else {
          this.showNotification("User not found", "error");
        }
      });
  }

  showGroupSettingsModal() {
    const group = this.currentGroup;
    const modal = document.getElementById("modalOverlay");
    modal.classList.remove("hidden");

    let dynamicModal = document.getElementById("dynamicModal");
      if (!dynamicModal) {
        dynamicModal = document.createElement("div");
        dynamicModal.id = "dynamicModal";
        dynamicModal.className = "modal";
        modal.appendChild(dynamicModal);
      }
      dynamicModal.innerHTML = `
            <div class="modal">
              <h3>Edit Group</h3>
              <input type="text" id="editGroupName" value="${group.name}" class="form-input">
              <textarea id="editGroupDesc" class="form-input">${group.description}</textarea>
              <div class="modal-footer">
                <button class="btn-secondary" onclick="app.closeModal()">Cancel</button>
                <button class="btn-primary" onclick="app.submitGroupEdit('${group.id}')">Save</button>
              </div>
            </div>`; // put your custom modal content here

  }

  submitGroupEdit(groupId) {
    const name = document.getElementById("editGroupName").value;
    const desc = document.getElementById("editGroupDesc").value;
    fetch("/api/edit_group", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group_id: groupId, name, description: desc })
    }).then(() => {
      this.showNotification("Group updated", "success");
      this.closeModal();
    });
  }

  loadInfoTab(type) {
    const infoContent = document.getElementById("infoContent");
    const entity = this.currentChat || this.currentGroup;
    if (!entity) return;

    
    if (type === "media") {
      fetch(`/api/messages?chat_type=${this.currentChat ? 'user' : 'group'}&chat_id=${entity.id}`)
        .then(res => res.json())
        .then(messages => {
          const media = messages.filter(m => m.message_type === "image" || m.message_type === "file");
          infoContent.innerHTML = media.length
            ? media.map(m => `
              <div class="media-item">
                ${m.message_type === "image" ? `<img src="${m.file_url}" onclick="window.open('${m.file_url}', '_blank')"/>` : `<a href="${m.file_url}" target="_blank">${m.file_name}</a>`}
              </div>`).join("")
            : "<p>No media shared yet.</p>";
        });
    }
  }


  showInfoPanel() {
    document.getElementById("infoPanel").classList.remove("hidden");
    this.loadInfoTab("about");
  }

  loadInfoTab(type) {
    const infoContent = document.getElementById("infoContent");
    const entity = this.currentChat || this.currentGroup;
    if (!entity) return;

    if (type === "about") {
      if (this.currentChat) {
        infoContent.innerHTML = `
          <div class="info-block">
            <h4>${entity.name}</h4>
            <p>@${entity.username}</p>
            <p>${entity.department || 'No department'}</p>
            <p>${entity.location || 'No location'}</p>
            <div class="action-buttons">
              <button class="btn-warning" onclick="app.blockUser('${entity.id}')">Block</button>
              <button class="btn-danger" onclick="app.reportUser('${entity.id}')">Report</button>
            </div>
          </div>`;
      } else if (this.currentGroup) {
        infoContent.innerHTML = `
          <div class="info-block">
            <h4>${entity.name}</h4>
            <p>${entity.description}</p>
            <p>Community: ${entity.community_name}</p>
            <div class="action-buttons">
              <button class="btn-secondary" onclick="app.leaveGroup('${entity.id}')">Leave Group</button>
              <button class="btn-primary" onclick="app.showPendingRequests('${entity.id}')">Requests</button>
              <button class="btn-primary" onclick="app.showAddMemberModal('${entity.id}')">Add Member</button>
            </div>
            <button onclick="app.showGroupSettingsModal()">Edit Group</button>
            <input type="text" id="memberSearch" placeholder="Search members" class="form-input">
            <div id="groupMemberList">Loading...</div>
          </div>`;

        fetch(`/api/group_members?group_id=${entity.id}`)
          .then(res => res.json())
          .then(members => {
            const list = members.map(m => `
              <div class="member-item">
                <span>${m.full_name} (@${m.username})</span>
                ${m.is_admin ? '<span class="badge">admin</span>' : ''}
              </div>`).join("");
            document.getElementById("groupMemberList").innerHTML = list;

            const input = document.getElementById("memberSearch");
            input.addEventListener("input", () => {
              const filtered = members.filter(m => m.full_name.toLowerCase().includes(input.value.toLowerCase()));
              document.getElementById("groupMemberList").innerHTML = filtered.map(m => `
                <div class="member-item">
                  <span>${m.full_name} (@${m.username})</span>
                  ${m.is_admin ? '<span class="badge">admin</span>' : ''}
                </div>`).join("");
            });
          });
      }
    }

    if (type === "media") {
      fetch(`/api/messages?chat_type=${this.currentChat ? 'user' : 'group'}&chat_id=${entity.id}`)
        .then(res => res.json())
        .then(messages => {
          const media = messages.filter(m => m.message_type === "image" || m.message_type === "file");
          infoContent.innerHTML = media.length
            ? media.map(m => `
              <div class="media-item">
                ${m.message_type === "image" ? `<img src="${m.file_url}" />` : `<a href="${m.file_url}">${m.file_name}</a>`}
              </div>`).join("")
            : "<p>No media shared yet.</p>";
        });
    }
  }

  // closeModal() {
  //   document.getElementById("modalOverlay").classList.add("hidden");
  //   document.getElementById("modalOverlay").innerHTML = "";
  // }

  closeInfoPanel() {
    document.getElementById("infoPanel").classList.add("hidden");
  }

  blockUser(userId) {
    fetch("/api/block_user", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId })
    }).then(() => this.showNotification("User blocked", "success"));
  }

  reportUser(userId) {
    fetch("/api/report_user", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId })
    }).then(() => this.showNotification("User reported", "success"));
  }

  leaveGroup(groupId) {
    fetch("/api/leave_group", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group_id: groupId })
    }).then(() => {
      this.showNotification("You left the group", "success");
      this.loadChatData();
      this.closeModal();
    });
  }

  showPendingRequests(groupId) {
    fetch(`/api/pending_requests?group_id=${groupId}`)
      .then(res => res.json())
      .then(requests => {
        const list = requests.map(req => `
          <div>
            <p>@${req.username} (${req.full_name})</p>
            <button onclick="app.acceptJoinRequest(${req.request_id})">Accept</button>
          </div>
        `).join("");
        document.getElementById("modalOverlay").classList.remove("hidden");
        document.getElementById("modalOverlay").innerHTML = `<div class="modal"><h3>Pending Requests</h3>${list}</div>`;
      });
  }

  acceptJoinRequest(requestId) {
    fetch("/api/accept_join_request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: requestId })
    }).then(() => this.showNotification("Request accepted", "success"));
  }

  promoteToAdmin(groupId, userId) {
    fetch("/api/promote_to_admin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group_id: groupId, user_id: userId })
    }).then(() => this.showNotification("User promoted to admin", "success"));
  }


  showAnnouncementPanel(communityId) {
    if (communityId) {
      this.currentCommunity = this.communities.find((c) => c.id == communityId)
    }

    const announcementPanel = document.getElementById("announcementPanel")
    announcementPanel.innerHTML = this.generateAnnouncementPanelHTML()
    announcementPanel.classList.remove("hidden")

    document.getElementById("sendAnnouncementBtn").addEventListener("click", () => {
      this.sendAnnouncement()
    })
  }

  generateAnnouncementPanelHTML() {
    return `
      <div class="info-header">
        <button class="header-btn" onclick="app.hideAnnouncementPanel()">
          <i class="fas fa-arrow-left"></i>
        </button>
        <h2>Community Announcements</h2>
      </div>
      <div class="announcement-composer">
        <div class="composer-header">
          <i class="fas fa-bullhorn"></i>
          <h3>Send Announcement</h3>
        </div>
        <textarea id="announcementTextarea" class="announcement-textarea" placeholder="Type your announcement to all groups in this community..."></textarea>
        <button id="sendAnnouncementBtn" class="announcement-send-btn">
          <i class="fas fa-bullhorn"></i>
          Send to All Groups
        </button>
      </div>
    `
  }

  sendAnnouncement() {
    const textarea = document.getElementById("announcementTextarea")
    const content = textarea.value.trim()
    if (!content || !this.currentCommunity) return

    this.socket.emit("send_announcement", {
      content: content,
      community_id: this.currentCommunity.id,
    })

    textarea.value = ""
    this.hideAnnouncementPanel()
  }

  hideAnnouncementPanel() {
    const announcementPanel = document.getElementById("announcementPanel")
    announcementPanel.classList.add("hidden")
  }

  // Utility functions
  formatTime(date) {
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)

    if (minutes < 1) return "now"
    if (minutes < 60) return `${minutes}m`
    if (hours < 24) return `${hours}h`
    return `${days}d`
  }

  formatMessageTime(date) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  }

  formatExpiry(date) {
    const now = new Date()
    const diff = date.getTime() - now.getTime()
    const days = Math.floor(diff / 86400000)
    const hours = Math.floor(diff / 3600000)

    if (days > 0) return `${days}d left`
    if (hours > 0) return `${hours}h left`
    return "Expiring soon"
  }






  loadFeed() {
    if (this.feedEnd || this.feedLoading) return;
    this.feedLoading = true;

    fetch(`/api/feed?page=${this.feedPage}`)
      .then(res => res.json())
      .then(posts => {
        const container = document.getElementById("feedContainer");
        if (posts.length === 0) {
          this.feedEnd = true;
          return;
        }
        container.innerHTML += posts.map(post => `
          <div class="post">
            <div class="post-header">${post.author}</div>
            <div class="post-body">${post.content}</div>
            <div class="post-time">${new Date(post.created_at).toLocaleString()}</div>
          </div>
        `).join("");
        this.feedPage++;
        this.feedLoading = false;
      });
  }

  showPostModal() {
    const modal = document.getElementById("modalOverlay");
    modal.classList.remove("hidden");
    modal.innerHTML = `
      <div id="dynamicModal" class="modal">
        <div class="modal-header">
          <h3>New Post</h3>
          <button onclick="app.closeModal()">&times;</button>
        </div>
        <div class="modal-body">
          <textarea id="postContent" class="form-input" rows="6" placeholder="Write something..."></textarea>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" onclick="app.closeModal()">Cancel</button>
          <button class="btn-primary" onclick="app.submitPost()">Post</button>
        </div>
      </div>`;
  }

  submitPost() {
    const content = document.getElementById("postContent").value.trim();
    if (!content) return this.showNotification("Post cannot be empty", "error");

    fetch("/api/feed/post", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content })
    }).then(res => res.json())
      .then(res => {
        if (res.success) {
          this.closeModal();
          this.feedPage = 1;
          this.feedEnd = false;
          document.getElementById("feedContainer").innerHTML = "";
          this.loadFeed();
        } else {
          this.showNotification("Failed to post", "error");
        }
      });
  }



  
}


// Initialize the application
let app
document.addEventListener("DOMContentLoaded", () => {
  app = new DockTalkApp()
})
