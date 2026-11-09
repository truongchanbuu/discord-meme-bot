"""Native Discord meme picker: ephemeral previews, selects and navigation buttons."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord

from meme_manager.domain.models import Meme
from meme_manager.domain.options import BotOptions

if TYPE_CHECKING:
    from meme_manager.discord_app.media import MemeMedia


class MemeOption(discord.ui.Select["MemePicker"]):
    def __init__(self, memes: list[Meme], selected_id: int) -> None:
        options = [
            discord.SelectOption(
                label=meme.title[:90],
                value=str(meme.id),
                description=f"#{meme.id} · {meme.media_kind} · {meme.filename[:70]}",
                default=meme.id == selected_id,
            )
            for meme in memes
        ]
        super().__init__(placeholder="Choose a meme", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert view is not None
        view.selected_id = int(self.values[0])
        view.refresh_controls()
        await interaction.response.defer()
        await view.show_preview(interaction)


class MemePicker(discord.ui.View):
    """Discord-native picker: select, previous/next and send to current channel."""

    def __init__(
        self, media: MemeMedia, memes: list[Meme], requester_id: int, options: BotOptions
    ) -> None:
        super().__init__(timeout=options.picker_timeout)
        self.options = options
        self.media = media
        self.memes = memes
        self.requester_id = requester_id
        self._preview_lock = asyncio.Lock()
        self.page = 0
        self.selected_id = memes[0].id
        self.refresh_controls()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message("Đây không phải menu của bạn.", ephemeral=True)
        return False

    def refresh_controls(self) -> None:
        self.clear_items()
        start = self.page * self.options.page_size
        current = self.memes[start : start + self.options.page_size]
        self.add_item(MemeOption(current, self.selected_id))
        self.previous_page.disabled = self.page == 0
        self.next_page.disabled = (start + self.options.page_size) >= len(self.memes)
        self.add_item(self.previous_page)
        self.add_item(self.next_page)
        self.add_item(self.post_to_channel)

    async def show_preview(self, interaction: discord.Interaction) -> None:
        async with self._preview_lock:
            upload_limit = (
                interaction.guild.filesize_limit
                if interaction.guild
                else self.options.preview_limit_bytes
            )
            upload_limit = getattr(interaction, "filesize_limit", upload_limit)
            embed, files = await self.preview(upload_limit)
            try:
                await interaction.edit_original_response(embed=embed, attachments=files, view=self)
            except discord.HTTPException:
                if not files:
                    raise
                embed.add_field(
                    name="Không tải được preview",
                    value="Hãy thử lại hoặc mở file gốc bằng liên kết ở trên.",
                )
                await interaction.edit_original_response(embed=embed, attachments=[], view=self)
            finally:
                for file in files:
                    file.close()

    async def preview(self, upload_limit: int) -> tuple[discord.Embed, list[discord.File]]:
        meme = next(item for item in self.memes if item.id == self.selected_id)
        embed = discord.Embed(
            title=f"#{meme.id} — {meme.title}",
            description=(
                f"{meme.media_kind.upper()} · {meme.tags or 'Chưa có tag'}\n"
                f"[Mở file gốc trong Discord]({meme.jump_url})"
            ),
        )
        embed.set_footer(
            text=f"Trang {self.page + 1}/{(len(self.memes) - 1) // self.options.page_size + 1}"
        )
        attachment = await self.media.get_attachment(meme)
        if attachment is None:
            embed.add_field(name="Lưu ý", value="File gốc đã mất hoặc bot thiếu quyền đọc.")
            return embed, []
        if meme.media_kind == "image":
            embed.set_image(url=attachment.url)
            return embed, []
        if attachment.size > upload_limit:
            embed.add_field(
                name="Video vượt giới hạn preview",
                value="Mở file gốc bằng liên kết ở trên để xem video.",
            )
            return embed, []
        try:
            file = await attachment.to_file(use_cached=False)
        except discord.HTTPException:
            embed.add_field(
                name="Không tải được video",
                value="Hãy thử lại hoặc mở file gốc bằng liên kết ở trên.",
            )
            return embed, []
        return embed, [file]

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary, row=1)
    async def previous_page(
        self, interaction: discord.Interaction, _: discord.ui.Button[MemePicker]
    ) -> None:
        self.page -= 1
        self.selected_id = self.memes[self.page * self.options.page_size].id
        self.refresh_controls()
        await interaction.response.defer()
        await self.show_preview(interaction)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(
        self, interaction: discord.Interaction, _: discord.ui.Button[MemePicker]
    ) -> None:
        self.page += 1
        self.selected_id = self.memes[self.page * self.options.page_size].id
        self.refresh_controls()
        await interaction.response.defer()
        await self.show_preview(interaction)

    @discord.ui.button(label="Send to channel", style=discord.ButtonStyle.primary, row=1)
    async def post_to_channel(
        self, interaction: discord.Interaction, _: discord.ui.Button[MemePicker]
    ) -> None:
        meme = next(item for item in self.memes if item.id == self.selected_id)
        await self.media.send_meme(interaction, meme)
