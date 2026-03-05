const { createApp, ref, computed, onMounted, watch } = Vue
const { createRouter, createWebHashHistory } = VueRouter

// ========================================
// I18n Helper - Get translations from Django
// ========================================
const getConfig = () => window.BREVO_ANALYTICS_CONFIG || { translations: {}, languageCode: 'en' }
const t = (key, fallback = key) => getConfig().translations[key] || fallback

const formatDate = (dateValue, options = null) => {
  if (!dateValue) return ''
  const locale = getConfig().languageCode === 'it' ? 'it-IT' : 'en-US'
  return new Date(dateValue).toLocaleDateString(locale, options || {
    day: 'numeric', month: 'long', year: 'numeric'
  })
}

const formatDateTime = (dateValue, options = null) => {
  if (!dateValue) return ''
  const locale = getConfig().languageCode === 'it' ? 'it-IT' : 'en-US'
  const d = new Date(dateValue)
  const datePart = d.toLocaleDateString(locale, options || {
    day: 'numeric', month: 'short', year: 'numeric'
  })
  const timePart = d.toLocaleTimeString(locale, {
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  })
  return `${datePart} - ${timePart}`
}

const formatShortDate = (dateValue) => {
  if (!dateValue) return ''
  const locale = getConfig().languageCode === 'it' ? 'it-IT' : 'en-US'
  return new Date(dateValue).toLocaleDateString(locale, {
    day: 'numeric', month: 'short', year: 'numeric'
  })
}

// ========================================
// API Helper
// ========================================
const api = {
  async get(url) {
    const response = await fetch(`/brevo-analytics${url}`)
    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`)
    }
    return response.json()
  },
  async delete(url) {
    const response = await fetch(`/brevo-analytics${url}`, {
      method: 'DELETE',
      headers: {
        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''
      }
    })
    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(errorData.error || response.statusText)
    }
    return response.json()
  }
}

// ========================================
// Shared Composables
// ========================================
const emailModal = {
  isOpen: ref(false),
  emailData: ref(null),
  loading: ref(false),

  async open(emailId) {
    this.isOpen.value = true
    this.loading.value = true
    try {
      this.emailData.value = await api.get(`/api/emails/${emailId}/`)
    } catch (error) {
      console.error('Failed to load email details:', error)
      alert(t('email_detail_load_error'))
      this.close()
    } finally {
      this.loading.value = false
    }
  },

  close() {
    this.isOpen.value = false
    this.emailData.value = null
  }
}

// ========================================
// Components
// ========================================

// Breadcrumb Component (not used - Django handles breadcrumbs now)
const Breadcrumb = {
  template: `
    <div class="breadcrumb">
      <router-link to="/">{{ t('dashboard_title') }}</router-link>
      <span v-if="text"> / {{ text }}</span>
    </div>
  `,
  props: ['text'],
  setup() {
    return { t }
  }
}

// Email Detail Modal Component
const EmailDetailModal = {
  template: `
    <div v-if="isOpen" class="modal-overlay" @click.self="close">
      <div class="modal-content">
        <div class="modal-header">
          <div>
            <h2>{{ email?.recipient_email }}</h2>
            <p>{{ email?.message.subject }} · {{ formatDate(email?.message.sent_date) }}</p>
          </div>
          <button class="modal-close" @click="close">×</button>
        </div>
        <div class="modal-body">
          <div v-if="loading" class="loading">{{ t('loading') }}</div>
          <div v-else-if="email">
            <!-- Blacklist Info Box -->
            <div
              v-if="email.current_status === 'blocked' && email.blacklist_info"
              class="blacklist-box"
              style="margin-bottom: 20px; padding: 16px; background: #fff3e0; border-left: 4px solid #ff9800; border-radius: 4px;">
              <h4 style="margin: 0 0 12px 0; color: #e65100; font-size: 15px;">🚫 Email in Blacklist Brevo</h4>
              <div style="font-size: 0.9em; color: #555; line-height: 1.6;">
                <div v-if="email.blacklist_info.reason">
                  <strong>Motivo:</strong> {{ formatBlacklistReason(email.blacklist_info.reason) }}
                </div>
                <div v-if="email.blacklist_info.blocked_at">
                  <strong>Data blocco:</strong> {{ formatDateTime(email.blacklist_info.blocked_at) }}
                </div>
                <div v-if="formatSenders(email.blacklist_info.senders)">
                  <strong>Senders bloccati:</strong> {{ formatSenders(email.blacklist_info.senders) }}
                </div>
              </div>
              <button
                v-if="!removingFromBlacklist"
                @click="removeFromBlacklist"
                style="margin-top: 12px; padding: 8px 16px; background: #ff9800; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 13px;">
                Rimuovi da Blacklist
              </button>
              <div v-else style="margin-top: 12px; color: #666; font-size: 13px;">
                Rimozione in corso...
              </div>
            </div>

            <h3 style="margin-bottom: 10px;">Timeline Eventi</h3>
            <div
              v-if="showOpenedInfo(email)"
              class="info-box"
              style="margin-bottom: 20px; padding: 12px; background: #f0f7ff; border-left: 4px solid #2196F3; font-size: 0.9em; color: #555;">
              <strong>ℹ️ Nota:</strong> L'evento "Aperta" si basa sul caricamento di un pixel invisibile.
              Può mancare o apparire dopo "Cliccata" se l'utente ha bloccato le immagini o ha cliccato prima del caricamento del pixel.
            </div>
            <div class="timeline">
              <div
                v-for="(event, index) in email.events"
                :key="index"
                class="timeline-event"
                :class="'event-' + event.type">
                <div class="timeline-marker"></div>
                <div class="timeline-content">
                  <div class="event-title">{{ eventLabel(event.type) }}</div>
                  <div class="event-time">{{ formatDateTime(event.timestamp) }}</div>

                  <div v-if="event.bounce_type" class="event-detail">
                    <strong>Tipo:</strong>
                    <span :class="event.bounce_type === 'hard' ? 'bounce-hard' : 'bounce-soft'">
                      {{ event.bounce_type === 'hard' ? 'Hard Bounce' : 'Soft Bounce' }}
                    </span>
                  </div>
                  <div v-if="event.bounce_reason" class="event-detail">
                    <strong>Motivo:</strong> {{ event.bounce_reason }}
                  </div>
                  <div v-if="event.link && event.link !== 'NA'" class="event-detail">
                    <strong>URL:</strong> <a :href="event.link" target="_blank">{{ event.link }}</a>
                  </div>
                  <div v-if="event.ip" class="event-detail">
                    <strong>IP:</strong> {{ event.ip }}
                  </div>
                  <div v-if="event.user_agent" class="event-detail">
                    <strong>User Agent:</strong> {{ event.user_agent }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,

  setup() {
    const isOpen = emailModal.isOpen
    const email = emailModal.emailData
    const loading = emailModal.loading
    const removingFromBlacklist = ref(false)

    const close = () => emailModal.close()

    const formatDate = (dateStr) => {
      if (!dateStr) return ''
      return new Date(dateStr).toLocaleDateString('it-IT', {
        day: 'numeric',
        month: 'long',
        year: 'numeric'
      })
    }

    const formatDateTime = (dateStr) => {
      if (!dateStr) return ''
      return new Date(dateStr).toLocaleString('it-IT', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      })
    }

    const eventLabel = (type) => {
      const labels = {
        'sent': t('sent_status'),
        'delivered': t('delivered_status'),
        'opened': t('opened_status'),
        'clicked': t('clicked_status'),
        'bounced': t('bounced_status'),
        'blocked': t('blocked_status'),
        'deferred': t('deferred_status'),
        'unsubscribed': t('unsubscribed_status')
      }
      return labels[type] || type
    }

    const formatBlacklistReason = (reason) => {
      // Handle objects/dicts - extract code first, fallback to message
      if (typeof reason === 'object' && reason !== null) {
        if (reason.code) {
          reason = reason.code
        } else if (reason.message) {
          reason = reason.message
        } else {
          reason = JSON.stringify(reason)
        }
      }

      // Ensure it's a string
      reason = String(reason || 'unknown')

      // Tabella traduzioni code Brevo → Italiano
      const translations = {
        // Hard bounces
        'hard_bounce': 'Hard Bounce',
        'hardBounce': 'Hard Bounce',
        'invalidEmail': 'Email Invalida',
        'blockedDomain': 'Dominio Bloccato',
        'unknown': 'Sconosciuto',

        // Soft bounces
        'soft_bounce': 'Soft Bounce',
        'softBounce': 'Soft Bounce',
        'mailboxFull': 'Casella Piena',
        'greyListed': 'Greylist',
        'temporaryUnavailable': 'Temporaneamente Non Disponibile',

        // Complaints
        'complaint': 'Segnalazione Spam',
        'spam': 'Spam',

        // Unsubscribes
        'unsubscribe': 'Disiscrizione',
        'unsubscribed': 'Disiscritto',
        'unsubscribedViaEmail': 'Disiscritto via Email',
        'unsubscribedViaLink': 'Disiscritto via Link',
        'unsubscribedViaAdmin': 'Disiscritto dall\'Amministratore',

        // Blocks
        'manual_block': 'Blocco Manuale',
        'blocked': 'Bloccato',
        'blockedContact': 'Contatto Bloccato',

        // Invalid
        'invalid_email': 'Email Invalida',
        'invalidDomain': 'Dominio Invalido',
        'invalidSyntax': 'Sintassi Invalida',

        // Deferred
        'deferred': 'Differita',

        // Errors
        'error': 'Errore',
        'errorRelaying': 'Errore di Inoltro'
      }

      return translations[reason] || reason
    }

    const formatSenders = (senders) => {
      if (!senders) return null
      if (Array.isArray(senders)) {
        return senders.length > 0 ? senders.join(', ') : null
      }
      // If it's a string, return as-is
      if (typeof senders === 'string') {
        return senders
      }
      return null
    }

    const removeFromBlacklist = async () => {
      if (!email.value || !email.value.recipient_email) return

      const confirmed = confirm(
        `Sei sicuro di voler rimuovere ${email.value.recipient_email} dalla blacklist?\n\n` +
        'Questa azione permetterà nuovamente l\'invio di email a questo indirizzo.'
      )

      if (!confirmed) return

      removingFromBlacklist.value = true

      try {
        const encodedEmail = encodeURIComponent(email.value.recipient_email)
        await api.delete(`/api/blacklist/${encodedEmail}/remove/`)

        alert('Email rimossa dalla blacklist con successo!')

        // Ricarica i dettagli email per aggiornare lo stato
        emailModal.close()

      } catch (error) {
        console.error('Error removing from blacklist:', error)
        alert(`Errore nella rimozione dalla blacklist: ${error.message}`)
      } finally {
        removingFromBlacklist.value = false
      }
    }

    const showOpenedInfo = (emailData) => {
      if (!emailData || !emailData.events) return false

      const eventTypes = emailData.events.map(e => e.type)
      const hasClicked = eventTypes.includes('clicked')
      const hasOpened = eventTypes.includes('opened')

      // Show info if:
      // 1. Has clicked but no opened event
      if (hasClicked && !hasOpened) return true

      // 2. Clicked appears before first opened
      if (hasClicked && hasOpened) {
        const firstClickedIndex = eventTypes.indexOf('clicked')
        const firstOpenedIndex = eventTypes.indexOf('opened')
        if (firstClickedIndex < firstOpenedIndex) return true
      }

      return false
    }

    return {
      isOpen,
      email,
      loading,
      removingFromBlacklist,
      close,
      t,
      formatDate,
      formatDateTime,
      eventLabel,
      formatBlacklistReason,
      formatSenders,
      removeFromBlacklist,
      showOpenedInfo
    }
  }
}

// Dashboard Component
const Dashboard = {
  template: `
    <div class="dashboard">
      <div v-if="loading" class="loading">{{ t('loading') }}</div>

      <div v-else>
        <!-- KPI Cards -->
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-label">{{ t('emails_sent') }}</div>
            <div class="kpi-value">{{ kpi.total_sent }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">{{ t('delivery_rate') }}</div>
            <div class="kpi-value">{{ kpi.delivery_rate }}%</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">{{ t('open_rate') }}</div>
            <div class="kpi-value">{{ kpi.open_rate }}%</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">{{ t('click_rate') }}</div>
            <div class="kpi-value">{{ kpi.click_rate }}%</div>
          </div>
          <div class="kpi-card clickable">
            <div class="kpi-label">{{ t('emails_bounced') }}</div>
            <div class="kpi-value">
              <router-link to="/emails/bounced">{{ kpi.total_bounced }}</router-link>
            </div>
          </div>
          <div class="kpi-card clickable">
            <div class="kpi-label">{{ t('emails_blocked') }}</div>
            <div class="kpi-value">
              <router-link to="/emails/blocked">{{ kpi.total_blocked }}</router-link>
            </div>
          </div>
        </div>

        <!-- Messages List -->
        <div class="section">
          <div class="messages-header">
            <h2>{{ showAll ? t('all_messages') : t('recent_messages') }}</h2>
            <a v-if="!showAll" href="#" @click.prevent="showAll = true" class="btn-link">
              {{ t('show_all') }}
            </a>
          </div>

          <table class="data-table">
            <thead>
              <tr>
                <th>{{ t('subject') }}</th>
                <th>{{ t('date') }}</th>
                <th>{{ t('sent') }}</th>
                <th>{{ t('delivery') }}</th>
                <th>{{ t('open') }}</th>
                <th>{{ t('click') }}</th>
                <th>{{ t('bounced') }}</th>
                <th>{{ t('blocked') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="msg in displayedMessages"
                :key="msg.id"
                @click="goToMessage(msg.id)">
                <td><strong>{{ msg.subject }}</strong></td>
                <td>{{ formatDate(msg.sent_date) }}</td>
                <td>{{ msg.total_sent }}</td>
                <td>
                  <span class="badge" :class="rateClass(msg.delivery_rate)">
                    {{ msg.delivery_rate }}%
                  </span>
                </td>
                <td>{{ msg.open_rate }}%</td>
                <td>{{ msg.click_rate }}%</td>
                <td>
                  <a v-if="msg.total_bounced > 0"
                     @click.stop
                     :href="'#/messages/' + msg.id + '/emails?status=bounced'">
                    {{ msg.total_bounced }}
                  </a>
                  <span v-else>0</span>
                </td>
                <td>
                  <a v-if="msg.total_blocked > 0"
                     @click.stop
                     :href="'#/messages/' + msg.id + '/emails?status=blocked'">
                    {{ msg.total_blocked }}
                  </a>
                  <span v-else>0</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `,

  setup() {
    const loading = ref(true)
    const kpi = ref({})
    const messages = ref([])
    const allMessages = ref([])
    const showAll = ref(false)

    const displayedMessages = computed(() => {
      return showAll.value ? allMessages.value : messages.value
    })

    onMounted(async () => {
      try {
        const data = await api.get('/api/dashboard/')
        kpi.value = data.kpi
        messages.value = data.recent_messages
      } catch (error) {
        console.error('Failed to load dashboard:', error)
        alert(t('load_error'))
      } finally {
        loading.value = false
      }
    })

    watch(showAll, async (value) => {
      if (value && allMessages.value.length === 0) {
        try {
          const data = await api.get('/api/messages/')
          allMessages.value = data.messages
        } catch (error) {
          console.error('Failed to load all messages:', error)
        }
      }
    })

    const rateClass = (rate) => {
      if (rate >= 95) return 'success'
      if (rate >= 90) return 'warning'
      return 'danger'
    }

    const goToMessage = (messageId) => {
      router.push(`/messages/${messageId}/emails`)
    }

    return {
      loading,
      kpi,
      messages,
      showAll,
      displayedMessages,
      t,
      formatDate: formatShortDate,  // Use global helper
      rateClass,
      goToMessage
    }
  },

  components: {
    Breadcrumb
  }
}

// Message Emails Component
const MessageEmails = {
  template: `
    <div class="message-emails">
      <Breadcrumb :text="breadcrumbText" />

      <div v-if="loading" class="loading">{{ t('loading') }}</div>

      <div v-else-if="message">
        <!-- KPI Bar -->
        <div class="kpi-bar">
          <div
            class="kpi-card"
            :class="{ active: activeFilter === 'sent' }"
            @click="setFilter('sent')">
            <div class="kpi-label">{{ t('sent_status') }}</div>
            <div class="kpi-value">{{ message.total_sent }}</div>
          </div>
          <div
            class="kpi-card"
            :class="{ active: activeFilter === 'delivered' }"
            @click="setFilter('delivered')">
            <div class="kpi-label">{{ t('delivered_status') }}</div>
            <div class="kpi-value">{{ message.total_delivered }}</div>
          </div>
          <div
            class="kpi-card"
            :class="{ active: activeFilter === 'opened' }"
            @click="setFilter('opened')">
            <div class="kpi-label">{{ t('opened_status') }}</div>
            <div class="kpi-value">{{ message.total_opened }}</div>
          </div>
          <div
            class="kpi-card"
            :class="{ active: activeFilter === 'clicked' }"
            @click="setFilter('clicked')">
            <div class="kpi-label">{{ t('clicked_status') }}</div>
            <div class="kpi-value">{{ message.total_clicked }}</div>
          </div>
          <div
            class="kpi-card"
            :class="{ active: activeFilter === 'bounced' }"
            @click="setFilter('bounced')">
            <div class="kpi-label">{{ t('bounced_status') }}</div>
            <div class="kpi-value">{{ message.total_bounced }}</div>
          </div>
          <div
            class="kpi-card"
            :class="{ active: activeFilter === 'blocked' }"
            @click="setFilter('blocked')">
            <div class="kpi-label">{{ t('blocked_status') }}</div>
            <div class="kpi-value">{{ message.total_blocked }}</div>
          </div>
        </div>

        <!-- Search -->
        <div class="search-box">
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="t('search_placeholder')"
            @input="filterEmails">
        </div>

        <!-- Emails Table -->
        <table class="data-table">
          <thead>
            <tr>
              <th>{{ t('recipient') }}</th>
              <th>{{ t('sent_datetime') }}</th>
              <th>{{ t('status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="email in filteredEmails"
              :key="email.id"
              @click="openEmailDetail(email.id)">
              <td>{{ email.recipient_email }}</td>
              <td>{{ formatDateTime(email.sent_at) }}</td>
              <td>
                <span class="status-badge" :class="'status-' + email.current_status">
                  {{ statusLabel(email.current_status) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `,

  setup() {
    const route = useRoute()
    const loading = ref(true)
    const message = ref(null)
    const emails = ref([])
    const searchQuery = ref('')
    const activeFilter = ref(null)
    const filteredEmails = ref([])

    const breadcrumbText = computed(() => {
      if (!message.value) return ''
      return `${message.value.subject} - ${formatDate(message.value.sent_date)}`
    })

    onMounted(async () => {
      const messageId = route.params.messageId
      const statusParam = route.query.status

      try {
        const data = await api.get(`/api/messages/${messageId}/emails/`)
        message.value = data.message
        emails.value = data.emails

        if (statusParam) {
          setFilter(statusParam)
        } else {
          filteredEmails.value = emails.value
        }
      } catch (error) {
        console.error('Failed to load message emails:', error)
        alert(t('load_error'))
      } finally {
        loading.value = false
      }
    })

    const setFilter = (status) => {
      if (activeFilter.value === status) {
        // Toggle off
        activeFilter.value = null
        filterEmails()
      } else {
        activeFilter.value = status
        filterEmails()
      }
    }

    const filterEmails = () => {
      let filtered = emails.value

      // Apply status filter
      // Note: 'sent' shows all emails since all emails have been sent
      if (activeFilter.value && activeFilter.value !== 'sent') {
        filtered = filtered.filter(e => e.current_status === activeFilter.value)
      }

      // Apply search
      if (searchQuery.value) {
        const query = searchQuery.value.toLowerCase()
        filtered = filtered.filter(e =>
          e.recipient_email.toLowerCase().includes(query)
        )
      }

      filteredEmails.value = filtered
    }

    const statusLabel = (status) => {
      const labels = {
        'sent': t('sent_status'),
        'delivered': t('delivered_status'),
        'opened': t('opened_status'),
        'clicked': t('clicked_status'),
        'bounced': t('bounced_status'),
        'blocked': t('blocked_status'),
        'deferred': t('deferred_status')
      }
      return labels[status] || status
    }

    const openEmailDetail = (emailId) => {
      emailModal.open(emailId)
    }

    return {
      loading,
      message,
      searchQuery,
      activeFilter,
      filteredEmails,
      breadcrumbText,
      t,
      setFilter,
      filterEmails,
      formatDate,
      formatDateTime,
      statusLabel,
      openEmailDetail
    }
  },

  components: {
    Breadcrumb
  }
}

// Global Emails Component (Bounced/Blocked)
const GlobalEmails = {
  template: `
    <div class="global-emails">
      <Breadcrumb :text="breadcrumbText" />

      <div v-if="loading" class="loading">{{ t('loading') }}</div>

      <div v-else>
        <!-- Search -->
        <div class="search-box">
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="t('search_placeholder')"
            @input="filterEmails">
        </div>

        <!-- Emails Table -->
        <table class="data-table">
          <thead>
            <tr>
              <th>{{ t('subject') }}</th>
              <th>{{ t('recipient') }}</th>
              <th>{{ t('sent_datetime') }}</th>
              <th>{{ t('status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="email in filteredEmails"
              :key="email.id"
              @click="openEmailDetail(email.id)">
              <td>
                <strong>{{ email.message.subject }}</strong><br>
                <small style="color: #999;">{{ formatDate(email.message.sent_date) }}</small>
              </td>
              <td>{{ email.recipient_email }}</td>
              <td>{{ formatDateTime(email.sent_at) }}</td>
              <td>
                <span class="status-badge" :class="'status-' + email.current_status">
                  {{ statusLabel(email.current_status) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `,

  props: ['type'],

  setup(props) {
    const loading = ref(true)
    const emails = ref([])
    const searchQuery = ref('')
    const filteredEmails = ref([])

    const breadcrumbText = computed(() => {
      return props.type === 'bounced' ? t('emails_bounced') : t('emails_blocked')
    })

    onMounted(async () => {
      try {
        const data = await api.get(`/api/emails/${props.type}/`)
        emails.value = data.emails
        filteredEmails.value = emails.value
      } catch (error) {
        console.error(`Failed to load ${props.type} emails:`, error)
        alert(t('load_error'))
      } finally {
        loading.value = false
      }
    })

    const filterEmails = () => {
      if (!searchQuery.value) {
        filteredEmails.value = emails.value
        return
      }

      const query = searchQuery.value.toLowerCase()
      filteredEmails.value = emails.value.filter(e =>
        e.recipient_email.toLowerCase().includes(query) ||
        e.message.subject.toLowerCase().includes(query)
      )
    }

    const statusLabel = (status) => {
      const labels = {
        'bounced': t('bounced_status'),
        'blocked': t('blocked_status')
      }
      return labels[status] || status
    }

    const openEmailDetail = (emailId) => {
      emailModal.open(emailId)
    }

    return {
      loading,
      searchQuery,
      filteredEmails,
      breadcrumbText,
      t,
      filterEmails,
      formatDate: formatShortDate,  // Use global helper
      formatDateTime,  // Use global helper
      statusLabel,
      openEmailDetail
    }
  },

  components: {
    Breadcrumb
  }
}

// ========================================
// Router Setup
// ========================================
const routes = [
  {
    path: '/',
    component: Dashboard
  },
  {
    path: '/messages/:messageId/emails',
    component: MessageEmails
  },
  {
    path: '/emails/bounced',
    component: GlobalEmails,
    props: { type: 'bounced' }
  },
  {
    path: '/emails/blocked',
    component: GlobalEmails,
    props: { type: 'blocked' }
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// Make router available globally for components
window.useRoute = () => {
  return router.currentRoute.value
}

// ========================================
// App Setup
// ========================================
const app = createApp({
  components: {
    EmailDetailModal
  }
})

app.use(router)
app.mount('#brevo-app')
