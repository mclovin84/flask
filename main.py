version: 1.0.0
sections:
  # Main entry point - handles all incoming calls
  main:
    - answer:
        # Answer immediately and set up recording
        max_duration: 3600  # 1 hour max call duration
    
    # Start recording immediately for compliance
    - record:
        format: mp3
        stereo: true
        direction: both
        terminators: []  # Don't stop on any key press
        background: true  # Continue recording in background
        action:
          # Webhook to process recording when complete
          url: "${webhook_base_url}/recording-complete"
          method: POST
          params:
            call_sid: "%{call_sid}"
            from: "%{from}"
            to: "%{to}"
            timestamp: "%{timestamp}"
    
    # Legal compliance notice
    - play:
        url: "say:Hello, you've reached ${business_name}. This call will be screened and recorded for quality and training purposes."
        voice: "en-US-Neural2-F"  # Google Cloud voice
    
    # Set call metadata for logging
    - set:
        call_start_time: "%{timestamp}"
        caller_number: "%{from}"
        called_number: "%{to}"
        call_sid: "%{call_sid}"
        call_status: "screening"
    
    # Check blocklist first (only specific numbers, not patterns)
    - goto: check_dynamic_blocklist
    
  # Dynamic blocklist check
  check_dynamic_blocklist:
    - request:
        url: "${webhook_base_url}/check-blocklist"
        method: POST
        headers:
          Content-Type: application/json
        body:
          caller_number: "%{from}"
          call_sid: "%{call_sid}"
        save_variables: true
    
    - switch:
        variable: "%{response_blocked}"
        case:
          "true":
            - goto: blocked_caller
          default:
            - goto: ai_screening
  
  # AI-powered call screening
  ai_screening:
    - ai:
        # Configure AI agent for screening
        post_prompt: |
          You are an intelligent call screening assistant for ${business_name}. Your job is to:
          1. Politely ask the caller for their name and the reason for their call
          2. Automatically detect and block spam/robocalls/solicitations
          3. Transfer legitimate calls to the owner
          
          Guidelines:
          - Be professional but friendly
          - If caller is silent for >3 seconds, mark as spam
          - Auto-block these types of calls:
            * Credit card/loan offers
            * Extended warranty calls  
            * Generic "lower your rates" calls
            * Robotic/pre-recorded messages
            * Callers who won't identify themselves
            * Medicare/insurance solicitations
            * "You've won a prize" calls
            * IRS/legal threat scams
          - Transfer these legitimate calls:
            * People who clearly state their name and valid business reason
            * Delivery notifications
            * Appointment confirmations
            * Return calls from known businesses
            * Personal calls with specific reasons
          
          After screening, you must set these variables:
          - screening_result: "transfer" or "block" (no voicemail option)
          - caller_name: The caller's stated name
          - call_reason: Brief summary of why they're calling
          - spam_confidence: 0-100 (100 = definitely spam)
        
        post_prompt_url: "${webhook_base_url}/ai-context"  # Optional: Dynamic context
        
        # AI conversation parameters
        params:
          max_duration: 60  # 1 minute max screening
          language: "en-US"
          voice: "en-US-Neural2-F"
          
        # SWML to execute after AI screening
        SWML:
          - request:
              # Log the screening result
              url: "${webhook_base_url}/log-screening"
              method: POST
              headers:
                Content-Type: application/json
              body:
                call_sid: "%{call_sid}"
                from: "%{from}"
                to: "%{to}"
                screening_result: "%{screening_result}"
                caller_name: "%{caller_name}"
                call_reason: "%{call_reason}"
                spam_confidence: "%{spam_confidence}"
                ai_transcript: "%{ai_transcript}"
          
          - switch:
              variable: "%{screening_result}"
              case:
                "transfer":
                  - goto: transfer_to_owner
                "block":
                  - goto: blocked_caller
                default:  # If AI messes up, default to blocking
                  - goto: blocked_caller
  
  # Transfer legitimate calls to owner
  transfer_to_owner:
    # Tell the caller they're being connected
    - play:
        url: "say:Thank you %{caller_name}. I'm connecting you now. Please hold."
        voice: "en-US-Neural2-F"
    
    # Play hold music while connecting
    - play:
        url: "https://example.com/hold-music.mp3"  # Replace with your hold music
        loop: 0  # Loop indefinitely
        background: true
    
    - connect:
        # IMPORTANT: Caller ID modification has limitations
        # Most carriers don't allow dynamic caller ID name (CNAM) updates
        # We can only pass the calling number, not custom text
        from: "%{from}"  # Shows the actual caller's number
        to: "${owner_phone_number}"
        timeout: 30
        # Whisper announcement when you answer (before connecting caller)
        url: "${webhook_base_url}/owner-whisper"
        headers:
          X-Caller-Name: "%{caller_name}"
          X-Call-Reason: "%{call_reason}"
          X-Caller-Number: "%{from}"
        
        # If owner doesn't answer
        on_status:
          - no-answer:
              - goto: send_to_voicemail
          - busy:
              - goto: send_to_voicemail
    
    # Log successful transfer
    - request:
        url: "${webhook_base_url}/log-event"
        method: POST
        body:
          call_sid: "%{call_sid}"
          event: "transferred"
          duration: "%{call_duration}"
    
    - hangup
  
  # Handle blocked callers
  blocked_caller:
    - play:
        url: "say:I'm sorry, but we're unable to take your call at this time. If you believe this is an error, please email ${support_email}. Goodbye."
        voice: "en-US-Neural2-F"
    
    - request:
        url: "${webhook_base_url}/log-event"
        method: POST
        body:
          call_sid: "%{call_sid}"
          event: "blocked"
          reason: "%{block_reason}"
    
    - hangup
  
  # Voicemail system
  send_to_voicemail:
    - play:
        url: "say:The person you're trying to reach is unavailable. Please leave a message after the beep and we'll get back to you as soon as possible."
        voice: "en-US-Neural2-F"
    
    - play:
        url: "https://example.com/beep.mp3"  # Replace with beep sound
    
    - record:
        beep: false
        format: mp3
        max_length: 180  # 3 minutes max
        finish_on_key: "#"
        action:
          url: "${webhook_base_url}/voicemail-complete"
          method: POST
          params:
            call_sid: "%{call_sid}"
            from: "%{from}"
            caller_name: "%{caller_name}"
            call_reason: "%{call_reason}"
    
    - play:
        url: "say:Thank you for your message. Goodbye."
        voice: "en-US-Neural2-F"
    
    - hangup

# Configuration variables (set via SignalWire dashboard or environment)
# ${webhook_base_url} - Your webhook handler base URL
# ${business_name} - Your business name for greetings
# ${owner_phone_number} - Number to forward legitimate calls to
# ${support_email} - Email for blocked caller support