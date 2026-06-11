"""
Database models for ChatBotAI
Defines the schema for guests, conversations, messages, properties, and AI settings
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import MetaData
from werkzeug.security import generate_password_hash, check_password_hash

# Naming convention for constraints (required for SQLite batch migrations)
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)
db = SQLAlchemy(metadata=metadata)


class User(UserMixin, db.Model):
    """Application user for team access"""
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(200), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    last_seen = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assigned_conversations = db.relationship('Conversation', backref='assigned_user', lazy='dynamic')
    sessions = db.relationship('UserSession', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.id}: {self.username}>'

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'display_name': self.display_name,
            'is_admin': self.is_admin,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class UserSession(db.Model):
    """Tracks user login sessions for online-time statistics"""
    __tablename__ = 'user_session'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_active_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def duration_minutes(self):
        """Session duration in minutes"""
        return (self.last_active_at - self.started_at).total_seconds() / 60.0

    def __repr__(self):
        return f'<UserSession {self.id}: user={self.user_id}>'


class PushSubscription(db.Model):
    """Web Push notification subscription for a user's browser/device"""
    __tablename__ = 'push_subscription'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    endpoint = db.Column(db.Text, unique=True, nullable=False)
    p256dh = db.Column(db.String(256), nullable=False)
    auth = db.Column(db.String(256), nullable=False)
    user_agent = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    user = db.relationship('User', backref=db.backref('push_subscriptions', cascade='all, delete-orphan', lazy='dynamic'))

    def __repr__(self):
        return f'<PushSubscription {self.id}: user={self.user_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'endpoint': self.endpoint,
            'user_agent': self.user_agent,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Guest(db.Model):
    """
    Central guest records with contact info across platforms.
    A single guest may communicate via multiple platforms (email, WhatsApp, Airbnb, etc.)
    """
    __tablename__ = 'guest'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    email = db.Column(db.String(255), unique=True, index=True)
    phone = db.Column(db.String(50), index=True)

    # Platform-specific identifiers
    whatsapp_id = db.Column(db.String(100), index=True)
    airbnb_id = db.Column(db.String(100), index=True)
    booking_id = db.Column(db.String(100), index=True)
    smoobu_guest_id = db.Column(db.String(100), index=True)

    # Engagement tracking
    first_contact = db.Column(db.DateTime, default=datetime.utcnow)
    last_contact = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    total_stays = db.Column(db.Integer, default=0)

    # Owner's private notes (not accessible to AI)
    notes = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    details = db.relationship('GuestDetail', backref='guest', lazy='dynamic', cascade='all, delete-orphan')
    conversations = db.relationship('Conversation', backref='guest', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Guest {self.id}: {self.name or self.email or "Unknown"}>'

    def to_dict(self):
        """Convert guest to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'whatsapp_id': self.whatsapp_id,
            'airbnb_id': self.airbnb_id,
            'booking_id': self.booking_id,
            'smoobu_guest_id': self.smoobu_guest_id,
            'first_contact': self.first_contact.isoformat() if self.first_contact else None,
            'last_contact': self.last_contact.isoformat() if self.last_contact else None,
            'total_stays': self.total_stays,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class GuestDetail(db.Model):
    """
    CRITICAL - Persistent memory storage for guest information.
    Stores extracted details like family members, pets, preferences, allergies, etc.
    This is what makes ChatBotAI special - permanent guest memory!
    """
    __tablename__ = 'guest_detail'

    id = db.Column(db.Integer, primary_key=True)
    guest_id = db.Column(db.Integer, db.ForeignKey('guest.id', ondelete='CASCADE'), nullable=False, index=True)

    # Detail classification
    detail_type = db.Column(db.String(50), nullable=False)  # family, pet, preference, allergy, interest, special_request
    detail_key = db.Column(db.String(100), nullable=False)  # e.g., "son", "dog", "floor", "food"
    detail_value = db.Column(db.String(500), nullable=False)  # e.g., "Lucas", "Max", "ground", "peanuts"

    # AI extraction metadata
    confidence = db.Column(db.Float, default=1.0)  # 0.0-1.0 AI confidence score
    source_message_id = db.Column(db.Integer, db.ForeignKey('message.id', ondelete='SET NULL'), nullable=True)
    extracted_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Composite index for fast queries
    __table_args__ = (
        db.Index('ix_guest_detail_guest_type', 'guest_id', 'detail_type'),
    )

    def __repr__(self):
        return f'<GuestDetail {self.detail_type}:{self.detail_key}={self.detail_value}>'

    def to_dict(self):
        """Convert detail to dictionary"""
        return {
            'id': self.id,
            'guest_id': self.guest_id,
            'detail_type': self.detail_type,
            'detail_key': self.detail_key,
            'detail_value': self.detail_value,
            'confidence': self.confidence,
            'source_message_id': self.source_message_id,
            'extracted_at': self.extracted_at.isoformat() if self.extracted_at else None
        }


class Conversation(db.Model):
    """
    Platform conversation threads.
    Groups messages by platform and maintains conversation state.
    """
    __tablename__ = 'conversation'

    id = db.Column(db.Integer, primary_key=True)
    guest_id = db.Column(db.Integer, db.ForeignKey('guest.id', ondelete='CASCADE'), nullable=False, index=True)

    # Platform information
    platform = db.Column(db.String(50), nullable=False)  # email, whatsapp, airbnb, booking
    platform_id = db.Column(db.String(255), unique=True, index=True)  # External conversation ID

    # Conversation metadata
    subject = db.Column(db.String(500))  # Email subject or conversation topic
    status = db.Column(db.String(50), default='active')  # active, closed, pending_owner

    # AI control (per-conversation toggle)
    ai_enabled = db.Column(db.Boolean, default=True)

    # Auto-respond: AI automatically replies to new guest messages
    auto_respond = db.Column(db.Boolean, default=False, server_default='0', nullable=False)

    # Unread tracking for inbox
    is_read = db.Column(db.Boolean, default=True, server_default='1', nullable=False)

    # Read cursor: points to the last message the user has seen
    last_read_message_id = db.Column(db.Integer, db.ForeignKey('message.id', ondelete='SET NULL', use_alter=True), nullable=True)

    # Sync watermark: timestamp of the newest synced message (for skipping old messages during platform sync)
    last_synced_message_at = db.Column(db.DateTime, nullable=True)

    # Escalation tracking
    escalated = db.Column(db.Boolean, default=False, server_default='0', nullable=False, index=True)
    escalated_at = db.Column(db.DateTime, nullable=True)

    # Cancellation tracking (set by Smoobu cancelReservation webhook).
    # When non-NULL, UI shows a "Storniert" label so the team can decide
    # if the conversation still needs attention. Conversation history,
    # AI behavior, and visibility are unchanged.
    cancelled_at = db.Column(db.DateTime, nullable=True)

    # Approval queue: skip the queue for this conversation
    auto_approve = db.Column(db.Boolean, default=False, nullable=False)

    # Conversation summary for AI context (cached)
    ai_summary = db.Column(db.Text, nullable=True)
    ai_summary_through_id = db.Column(db.Integer, nullable=True)

    # User assignment (optional - NULL means visible to all)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)

    # Smoobu reservation link
    smoobu_reservation_id = db.Column(db.String(100), index=True)

    # Reservation stay dates (from Smoobu)
    check_in = db.Column(db.Date, nullable=True)
    check_out = db.Column(db.Date, nullable=True)

    # Property association (optional)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id', ondelete='SET NULL'), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Polling tripwire: bumped whenever ANY change should refresh inbox clients
    # (new message, out-of-order sync, owner reply). Do NOT use for ordering.
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Sort key: timestamp of the most recent message in this conversation.
    # Mirrors MAX(Message.sent_at). Used for inbox ordering — matches Smoobu order.
    last_message_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    messages = db.relationship('Message', backref='conversation', lazy='dynamic', cascade='all, delete-orphan',
                               order_by='Message.sent_at', foreign_keys='Message.conversation_id')

    def __repr__(self):
        return f'<Conversation {self.id}: {self.platform} - {self.subject or "No subject"}>'

    def to_dict(self, include_messages=False):
        """Convert conversation to dictionary"""
        lm = self.last_message  # Call once to avoid double query
        data = {
            'id': self.id,
            'guest_id': self.guest_id,
            'platform': self.platform,
            'display_platform': self.display_platform,
            'platform_id': self.platform_id,
            'subject': self.subject,
            'status': self.status,
            'ai_enabled': self.ai_enabled,
            'auto_respond': self.auto_respond,
            'is_read': self.is_read,
            'unread_count': self.unread_count,
            'last_read_message_id': self.last_read_message_id,
            'smoobu_reservation_id': self.smoobu_reservation_id,
            'user_id': self.user_id,
            'escalated': self.escalated,
            'escalated_at': self.escalated_at.isoformat() if self.escalated_at else None,
            'cancelled_at': self.cancelled_at.isoformat() if self.cancelled_at else None,
            'auto_approve': self.auto_approve,
            'assigned_user_name': self.assigned_user.display_name if self.assigned_user else None,
            'property_id': self.property_id,
            'property_name': self.property.name if self.property else None,
            'check_in': self.check_in.isoformat() if self.check_in else None,
            'check_out': self.check_out.isoformat() if self.check_out else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_message_at': self.last_message_at.isoformat() if self.last_message_at else None,
            'guest': self.guest.to_dict() if self.guest else None,
            'last_message': lm.to_dict() if lm else None
        }
        if include_messages:
            data['messages'] = [m.to_dict() for m in self.messages.all()]
        return data

    @property
    def last_message(self):
        """Get the most recent message in this conversation.
        Uses preloaded cache if available (set by preload_last_messages()).
        """
        if hasattr(self, '_cached_last_message'):
            return self._cached_last_message
        return self.messages.order_by(Message.sent_at.desc()).first()

    @property
    def message_count(self):
        """Get total number of messages.
        Uses preloaded cache if available (set by guest_profile route).
        """
        if hasattr(self, '_cached_message_count'):
            return self._cached_message_count
        return self.messages.count()

    @property
    def unread_count(self):
        """Count guest messages newer than the read cursor."""
        if hasattr(self, '_cached_unread_count'):
            return self._cached_unread_count
        query = self.messages.filter(Message.sender_type == 'guest')
        if self.last_read_message_id:
            query = query.filter(Message.id > self.last_read_message_id)
        return query.count()

    @property
    def display_platform(self):
        """Return the actual booking platform (e.g. 'Airbnb', 'Booking.com') if known,
        otherwise fall back to the raw platform name."""
        if hasattr(self, '_cached_display_platform'):
            return self._cached_display_platform
        if self.platform == 'smoobu' and self.guest:
            channel = GuestDetail.query.filter_by(
                guest_id=self.guest_id,
                detail_key='booking_channel'
            ).first()
            if channel and channel.detail_value:
                return channel.detail_value
        return self.platform.capitalize()

    def recompute_is_read(self):
        """Recompute is_read from the read cursor. Returns True if state changed."""
        has_unread = self.messages.filter(
            Message.sender_type == 'guest',
            Message.id > (self.last_read_message_id or 0)
        ).first() is not None
        new_is_read = not has_unread
        if self.is_read != new_is_read:
            self.is_read = new_is_read
            return True
        return False


class Message(db.Model):
    """
    Individual messages with processing status.
    Tracks sender type and whether memory extraction has been performed.
    """
    __tablename__ = 'message'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id', ondelete='CASCADE'), nullable=False, index=True)

    # Message content
    sender_type = db.Column(db.String(20), nullable=False, index=True)  # guest, owner, ai
    content = db.Column(db.Text, nullable=False)

    # Platform reference
    platform_message_id = db.Column(db.String(255))  # External platform message ID

    # Processing status
    is_processed = db.Column(db.Boolean, default=False, index=True)  # Has memory extraction run?

    # Approval queue
    approval_status = db.Column(db.String(20), nullable=True, index=True)  # NULL, 'pending', 'approved', 'rejected'
    approved_at = db.Column(db.DateTime, nullable=True)
    original_content = db.Column(db.Text, nullable=True)  # Deferred: populated by future "Learn from Corrections" feature (#8)

    # Source tracking
    sent_via_app = db.Column(db.Boolean, default=False)  # True = sent through ChatBotAI, False = synced from external platform
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)  # Which team member sent this message

    # Timestamps
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    extracted_details = db.relationship('GuestDetail', backref='source_message', lazy='dynamic')
    sender_user = db.relationship('User', foreign_keys=[user_id], lazy='select')

    def __repr__(self):
        preview = self.content[:50] + '...' if len(self.content) > 50 else self.content
        return f'<Message {self.id}: [{self.sender_type}] {preview}>'

    def to_dict(self):
        """Convert message to dictionary"""
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender_type': self.sender_type,
            'content': self.content,
            'platform_message_id': self.platform_message_id,
            'is_processed': self.is_processed,
            'approval_status': self.approval_status,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'original_content': self.original_content,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'user_id': self.user_id,
            'sender_name': self.sender_user.display_name if self.sender_user else None,
        }


class Property(db.Model):
    """
    Rental property information for AI context.
    Provides property details to help AI generate relevant responses.
    """
    __tablename__ = 'property'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    smoobu_apartment_id = db.Column(db.String(100), unique=True, index=True)
    address = db.Column(db.Text)
    description = db.Column(db.Text)

    # Property features (stored as JSON array)
    amenities = db.Column(db.JSON, default=list)  # ["wifi", "pool", "parking", "gym"]

    # Property specifications
    pet_friendly = db.Column(db.Boolean, default=False)
    max_guests = db.Column(db.Integer, default=4)
    bedrooms = db.Column(db.Integer, default=1)
    bathrooms = db.Column(db.Float, default=1.0)

    # Pricing
    price_per_night = db.Column(db.Float)

    # Check-in/out
    check_in_time = db.Column(db.String(20), default='3:00 PM')
    check_out_time = db.Column(db.String(20), default='11:00 AM')

    # Rules
    house_rules = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    conversations = db.relationship('Conversation', backref='property', lazy='dynamic')

    def __repr__(self):
        return f'<Property {self.id}: {self.name}>'

    def to_dict(self):
        """Convert property to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'smoobu_apartment_id': self.smoobu_apartment_id,
            'address': self.address,
            'description': self.description,
            'amenities': self.amenities,
            'pet_friendly': self.pet_friendly,
            'max_guests': self.max_guests,
            'bedrooms': self.bedrooms,
            'bathrooms': self.bathrooms,
            'price_per_night': self.price_per_night,
            'check_in_time': self.check_in_time,
            'check_out_time': self.check_out_time,
            'house_rules': self.house_rules,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ReplyTemplate(db.Model):
    """
    Quick reply templates (canned responses) for common messages.
    Supports variable substitution: {guest_name}, {property_name}, {check_in_time}
    """
    __tablename__ = 'reply_template'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), default='general')

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<ReplyTemplate {self.id}: {self.name}>'

    def to_dict(self):
        """Convert template to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'content': self.content,
            'category': self.category,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class AISettings(db.Model):
    """
    Flexible configuration storage for AI behavior.
    Key-value store for various AI settings.
    """
    __tablename__ = 'ai_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)  # Can store JSON for complex values
    description = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<AISettings {self.key}={self.value}>'

    def to_dict(self):
        """Convert setting to dictionary"""
        return {
            'id': self.id,
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def get(cls, key, default=None):
        """Get a setting value by key"""
        setting = cls.query.filter_by(key=key).first()
        return setting.value if setting else default

    @classmethod
    def set(cls, key, value, description=None):
        """Set a setting value"""
        setting = cls.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            setting = cls(key=key, value=value, description=description)
            db.session.add(setting)
        db.session.commit()
        return setting


class EmailBackfillCandidate(db.Model):
    """A guest message found in an Airbnb/Booking notification email that may be
    missing from a conversation. High-confidence matches are inserted directly;
    low-confidence ones land here for one-click review. See
    docs/superpowers/specs/2026-06-09-email-reconciliation-design.md.
    """
    __tablename__ = 'email_backfill_candidate'

    id = db.Column(db.Integer, primary_key=True)
    # Idempotency: one candidate per source email. Prevents re-queuing on re-scan.
    gmail_message_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    platform = db.Column(db.String(20), nullable=False)  # 'airbnb' | 'booking'
    parsed_name = db.Column(db.String(255))
    parsed_text = db.Column(db.Text)
    parsed_timestamp = db.Column(db.DateTime)
    guessed_conversation_id = db.Column(
        db.Integer, db.ForeignKey('conversation.id', ondelete='SET NULL'), nullable=True
    )
    confidence = db.Column(db.Float, default=0.0)
    # 'pending' | 'confirmed' | 'rejected'
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'gmail_message_id': self.gmail_message_id,
            'platform': self.platform,
            'parsed_name': self.parsed_name,
            'parsed_text': self.parsed_text,
            'parsed_timestamp': self.parsed_timestamp.isoformat() if self.parsed_timestamp else None,
            'guessed_conversation_id': self.guessed_conversation_id,
            'confidence': self.confidence,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<EmailBackfillCandidate {self.platform} {self.status} conf={self.confidence}>'


class KnowledgeEntry(db.Model):
    """
    Structured facts for AI context.
    Stores host knowledge (WiFi, check-in procedures, nearby places, etc.)
    that the AI references when responding to guests.
    Entries can be global (property_id=NULL) or per-property.
    """
    __tablename__ = 'knowledge_entry'

    VALID_CATEGORIES = [
        'general', 'checkin_checkout', 'nearby',
        'house_rules', 'emergency', 'faq', 'escalation', 'correction'
    ]

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id', ondelete='CASCADE'), nullable=True, index=True)
    category = db.Column(db.String(50), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    value = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Composite index for AI context queries
    __table_args__ = (
        db.Index('ix_knowledge_entry_property_category', 'property_id', 'category'),
    )

    # Relationship
    property = db.relationship('Property', backref=db.backref('knowledge_entries', cascade='all, delete-orphan', lazy='dynamic'))

    def __repr__(self):
        scope = f'property={self.property_id}' if self.property_id else 'global'
        return f'<KnowledgeEntry {self.id}: [{self.category}] {self.label} ({scope})>'

    def to_dict(self):
        return {
            'id': self.id,
            'property_id': self.property_id,
            'property_name': self.property.name if self.property else None,
            'category': self.category,
            'label': self.label,
            'value': self.value,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


def preload_last_messages(conversations):
    """Preload last message for a batch of conversations in ONE query (eliminates N+1).

    Sets _cached_last_message on each conversation object so that
    conversation.last_message and conversation.to_dict() use the cache
    instead of issuing individual queries.
    """
    if not conversations:
        return

    from sqlalchemy import func
    from sqlalchemy.orm import joinedload

    conv_ids = [c.id for c in conversations]

    # Single query: get the ID of the newest non-pending/non-rejected message per conversation
    last_msg_subq = db.session.query(
        Message.conversation_id,
        func.max(Message.id).label('last_msg_id')
    ).filter(
        Message.conversation_id.in_(conv_ids),
        db.or_(Message.approval_status.is_(None), Message.approval_status == 'approved')
    ).group_by(Message.conversation_id).subquery()

    # Fetch full Message objects for those IDs (eagerly load sender_user for display)
    last_messages = db.session.query(Message).options(
        joinedload(Message.sender_user)
    ).join(
        last_msg_subq, Message.id == last_msg_subq.c.last_msg_id
    ).all()

    msg_map = {m.conversation_id: m for m in last_messages}

    for c in conversations:
        c._cached_last_message = msg_map.get(c.id)


def preload_unread_counts(conversations):
    """Batch-load unread counts for a list of conversations.

    Sets _cached_unread_count on each conversation so that
    conversation.unread_count uses the cache instead of per-conversation queries.
    """
    if not conversations:
        return

    from sqlalchemy import func

    conv_ids = [c.id for c in conversations]

    # Single query: count unread guest messages per conversation
    rows = db.session.query(
        Message.conversation_id,
        func.count(Message.id)
    ).join(
        Conversation, Message.conversation_id == Conversation.id
    ).filter(
        Message.conversation_id.in_(conv_ids),
        Message.sender_type == 'guest'
    ).filter(
        db.or_(
            Conversation.last_read_message_id.is_(None),
            Message.id > Conversation.last_read_message_id
        )
    ).group_by(Message.conversation_id).all()

    counts = {conv_id: count for conv_id, count in rows}

    for c in conversations:
        c._cached_unread_count = counts.get(c.id, 0)


def preload_display_platforms(conversations):
    """Batch-load booking channel names for Smoobu conversations.

    Sets _cached_display_platform on each conversation so that
    conversation.display_platform uses the cache instead of per-conversation queries.
    """
    if not conversations:
        return

    smoobu_convs = [c for c in conversations if c.platform == 'smoobu' and c.guest_id]
    if not smoobu_convs:
        for c in conversations:
            c._cached_display_platform = c.platform.capitalize()
        return

    guest_ids = [c.guest_id for c in smoobu_convs]
    channels = GuestDetail.query.filter(
        GuestDetail.guest_id.in_(guest_ids),
        GuestDetail.detail_key == 'booking_channel'
    ).all()
    channel_map = {ch.guest_id: ch.detail_value for ch in channels}

    for c in conversations:
        if c.platform == 'smoobu' and c.guest_id:
            c._cached_display_platform = channel_map.get(c.guest_id) or 'Smoobu'
        else:
            c._cached_display_platform = c.platform.capitalize()


def init_db(app):
    """Initialize the database with the Flask app"""
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _populate_default_settings()


def _populate_default_settings():
    """Populate default AI settings if not present"""
    defaults = [
        ('ai_response_tone', 'friendly_professional', 'Tone for AI-generated responses'),
        ('auto_response_enabled', 'false', 'Enable automatic AI responses to guest messages'),
        ('memory_extraction_enabled', 'true', 'Enable extraction of guest information from messages'),
        ('max_conversation_history', '10', 'Maximum number of messages to include in AI context'),
        ('host_instructions', '', 'Custom instructions for AI responses (e.g. WiFi password, house rules, discounts)'),
        ('master_ai_enabled', 'false', 'Master switch: when OFF, no auto-responses anywhere'),
        ('auto_respond_new_conversations', 'false', 'Default auto-respond setting for newly created conversations'),
        ('ai_temperature', '0.3', 'AI response temperature (0.0 = deterministic, 1.0 = creative)'),
        ('ai_max_tokens', '1024', 'Maximum tokens per AI response (128-4096)'),
        ('approval_queue_enabled', 'true', 'AI responses require host approval before sending'),
        ('auto_approve_new_conversations', 'false', 'New conversations auto-approve AI responses (skip queue)'),
    ]

    # Load all existing settings in one query
    existing = {s.key: s for s in AISettings.query.all()}

    for key, value, description in defaults:
        if key not in existing:
            db.session.add(AISettings(key=key, value=value, description=description))

    # Ensure auto-respond settings are OFF for safe manual testing
    safe_off_keys = ['master_ai_enabled', 'auto_respond_new_conversations', 'auto_response_enabled']
    for key in safe_off_keys:
        setting = existing.get(key)
        if setting and setting.value == 'true':
            setting.value = 'false'

    db.session.commit()
