"""
Database models for ChatBotAI
Defines the schema for guests, conversations, messages, properties, and AI settings
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData

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

    # Unread tracking for inbox
    is_read = db.Column(db.Boolean, default=True, server_default='1', nullable=False)

    # Property association (optional)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id', ondelete='SET NULL'), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    messages = db.relationship('Message', backref='conversation', lazy='dynamic', cascade='all, delete-orphan',
                               order_by='Message.sent_at')

    def __repr__(self):
        return f'<Conversation {self.id}: {self.platform} - {self.subject or "No subject"}>'

    def to_dict(self, include_messages=False):
        """Convert conversation to dictionary"""
        data = {
            'id': self.id,
            'guest_id': self.guest_id,
            'platform': self.platform,
            'platform_id': self.platform_id,
            'subject': self.subject,
            'status': self.status,
            'ai_enabled': self.ai_enabled,
            'is_read': self.is_read,
            'property_id': self.property_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'guest': self.guest.to_dict() if self.guest else None,
            'last_message': self.last_message.to_dict() if self.last_message else None
        }
        if include_messages:
            data['messages'] = [m.to_dict() for m in self.messages.all()]
        return data

    @property
    def last_message(self):
        """Get the most recent message in this conversation"""
        return self.messages.order_by(Message.sent_at.desc()).first()

    @property
    def message_count(self):
        """Get total number of messages"""
        return self.messages.count()


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

    # Timestamps
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to extracted details (for audit trail)
    extracted_details = db.relationship('GuestDetail', backref='source_message', lazy='dynamic')

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
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Property(db.Model):
    """
    Rental property information for AI context.
    Provides property details to help AI generate relevant responses.
    """
    __tablename__ = 'property'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
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
        ('auto_response_enabled', 'true', 'Enable automatic AI responses to guest messages'),
        ('memory_extraction_enabled', 'true', 'Enable extraction of guest information from messages'),
        ('max_conversation_history', '10', 'Maximum number of messages to include in AI context'),
    ]

    for key, value, description in defaults:
        existing = AISettings.query.filter_by(key=key).first()
        if not existing:
            setting = AISettings(key=key, value=value, description=description)
            db.session.add(setting)

    db.session.commit()
