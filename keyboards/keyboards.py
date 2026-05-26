from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models.models import AVAILABLE_HASHTAGS


def start_keyboard(has_profile: bool = False, is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_profile:
        builder.row(
            InlineKeyboardButton(text="Submit a Moment", callback_data="submit_photo"),
            InlineKeyboardButton(text="My Profile", callback_data="my_profile"),
        )
        builder.row(
            InlineKeyboardButton(text="Edit Profile", callback_data="edit_profile_menu"),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="Create Profile", callback_data="create_profile"),
            InlineKeyboardButton(text="Submit a Moment", callback_data="submit_photo"),
        )
        builder.row(
            InlineKeyboardButton(text="My Profile", callback_data="my_profile"),
        )
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="🛠 Admin Panel", callback_data="admin_panel_root"),
        )
    builder.row(
        InlineKeyboardButton(text="View Guidelines", callback_data="guidelines"),
    )
    return builder.as_markup()


def profile_credit_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="My @username", callback_data="credit_username"),
        InlineKeyboardButton(text="My channel", callback_data="credit_channel"),
        InlineKeyboardButton(text="Stay anonymous", callback_data="credit_anonymous"),
    )
    return builder.as_markup()


def profile_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Looks good ✓", callback_data="profile_confirm"),
        InlineKeyboardButton(text="Change Answers", callback_data="profile_edit"),
    )
    return builder.as_markup()


def profile_view_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Edit Profile", callback_data="edit_profile_menu"),
        InlineKeyboardButton(text="← Back", callback_data="back_to_start"),
    )
    return builder.as_markup()


def profile_edit_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Edit Name", callback_data="edit_name"),
        InlineKeyboardButton(text="Edit Credit", callback_data="edit_credit"),
    )
    builder.row(
        InlineKeyboardButton(text="Edit Bio", callback_data="edit_bio"),
        InlineKeyboardButton(text="Back to Profile", callback_data="my_profile"),
    )
    return builder.as_markup()


def submission_add_more_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Add caption", callback_data="add_caption"),
        InlineKeyboardButton(text="Add location", callback_data="add_location"),
    )
    builder.row(
        InlineKeyboardButton(text="Submit as is", callback_data="submit_confirm"),
        InlineKeyboardButton(text="Cancel", callback_data="submit_cancel"),
    )
    return builder.as_markup()


def submission_skip_keyboard(skip_callback: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Skip ⏭", callback_data=skip_callback),
        InlineKeyboardButton(text="Cancel", callback_data="submit_cancel"),
    )
    return builder.as_markup()


def submission_hashtag_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tag in AVAILABLE_HASHTAGS:
        label = f"✓ #{tag}" if tag in selected else f"#{tag}"
        builder.button(text=label, callback_data=f"tag_{tag}")
    builder.adjust(3)
    builder.row(
        InlineKeyboardButton(text="✅ Done", callback_data="tags_done"),
        InlineKeyboardButton(text="Skip ⏭", callback_data="tags_skip"),
        InlineKeyboardButton(text="Cancel", callback_data="submit_cancel"),
    )
    return builder.as_markup()


def submission_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Submit →", callback_data="submit_confirm"),
        InlineKeyboardButton(text="Cancel", callback_data="submit_cancel"),
    )
    return builder.as_markup()


def admin_review_keyboard(submission_id: int, is_super_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Approve",
            callback_data=f"admin_approve_{submission_id}",
        ),
        InlineKeyboardButton(
            text="❌ Reject",
            callback_data=f"admin_reject_{submission_id}",
        ),
    )
    if is_super_admin:
        builder.row(
            InlineKeyboardButton(
                text="✏️ Edit caption",
                callback_data=f"admin_edit_{submission_id}",
            ),
            InlineKeyboardButton(
                text="📌 Feature candidate",
                callback_data=f"admin_feature_{submission_id}",
            ),
        )
        builder.row(
            InlineKeyboardButton(
                text="🚫 Ban user",
                callback_data=f"admin_ban_{submission_id}",
            ),
        )
    return builder.as_markup()


def back_to_start_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="← Back", callback_data="back_to_start"))
    return builder.as_markup()


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👥 Admins", callback_data="admin_panel_admins"),
        InlineKeyboardButton(text="🚫 Bans", callback_data="admin_panel_bans"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 Users", callback_data="admin_panel_users"),
        InlineKeyboardButton(text="📥 Pending", callback_data="admin_panel_pending"),
    )
    builder.row(
        InlineKeyboardButton(text="✖ Close", callback_data="admin_panel_close"),
    )
    return builder.as_markup()


def admin_manage_admins_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Add admin", callback_data="admin_action_add_admin"),
        InlineKeyboardButton(text="➖ Remove admin", callback_data="admin_action_remove_admin"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 List admins", callback_data="admin_action_list_admins"),
    )
    builder.row(
        InlineKeyboardButton(text="← Back", callback_data="admin_panel_root"),
    )
    return builder.as_markup()


def admin_manage_bans_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🚫 Ban user", callback_data="admin_action_ban"),
        InlineKeyboardButton(text="✅ Unban user", callback_data="admin_action_unban"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 List banned", callback_data="admin_action_list_banned"),
    )
    builder.row(
        InlineKeyboardButton(text="← Back", callback_data="admin_panel_root"),
    )
    return builder.as_markup()


def admin_cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✖ Cancel", callback_data="admin_panel_root"),
    )
    return builder.as_markup()


def admin_back_to_panel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="← Back to panel", callback_data="admin_panel_root"),
    )
    return builder.as_markup()
