# Cấu hình YAML

Cấu hình mặc định nằm trong package tại `src/meme_manager/config/`, được đọc theo
vị trí package, không phụ thuộc thư mục chạy lệnh. YAML được đóng gói khi build wheel.
Cấu hình được đọc và kiểm tra khi khởi động;
đổi YAML cần khởi động lại bot để áp dụng và đồng bộ các lựa chọn slash command.

| File | Cấu hình |
| --- | --- |
| `src/meme_manager/config/bot.yaml` | Tên nhóm thư viện, giới hạn import lịch sử, số kết quả mỗi trang, timeout picker, giới hạn preview dự phòng, mức/định dạng log và tên biến môi trường chứa token/server ID |
| `src/meme_manager/config/database.yaml` | Đường dẫn SQLite mặc định, tên biến môi trường ghi đè đường dẫn, timeout, batch đọc và độ dài tên/tag/caption |
| `src/meme_manager/config/search.yaml` | Giới hạn kết quả/từ truy vấn, điều kiện fuzzy, ngân sách lỗi gõ, số từ ghép và dung lượng cache chuẩn hóa |
| `src/meme_manager/config/media.yaml` | Category mặc định cho file ở gốc folder, nhóm định dạng, extension, loại media và trạng thái cho phép nhập |

Token và server ID vẫn lấy từ `.env`/environment theo tên trong `bot.yaml`.
`MEME_DB_PATH`, nếu có, ghi đè `database.path` để tiếp tục dùng DB hiện tại.
Đường dẫn DB tương đối được tính từ thư mục chạy lệnh. Không đưa token vào YAML đã commit.
Có thể đặt `MEME_CONFIG_DIR=/absolute/path/to/config` trong environment hoặc `.env` để
chọn bộ YAML khác cho cả bot và CLI. Thư mục đó cần đủ bốn file; không có fallback âm thầm.

## Service đọc config theo tên

```python
from meme_manager.services.config import ConfigService
from meme_manager.config import RuntimeConfig

service = ConfigService()
search_values = service.load("search")  # đọc src/meme_manager/config/search.yaml thành dict
runtime = RuntimeConfig.load()  # đọc đủ file, kiểm tra kiểu và tạo options có type
```

`load()` nhận basename, không nhận đường dẫn hoặc đuôi `.yaml`. File thiếu, YAML lỗi,
mapping không hợp lệ, option thiếu/thừa, sai kiểu hoặc giá trị ngoài giới hạn sẽ báo lỗi.
Parser dùng PyYAML SafeLoader; không chạy constructor Python trong YAML. Không cache nội
dung file trong service đọc; các options của một lần chạy được truyền vào từng thành phần.
Cache của search chỉ chứa chuỗi đã chuẩn hóa và có giới hạn trong `search.yaml`.

## Định dạng được nhập và bộ lọc kết quả

Ví dụ trong `media.yaml`:

```yaml
default_category: general
types:
  jpg:
    kind: image
    extensions: [jpg, jpeg]
    enabled: true
  gif:
    kind: image
    extensions: [gif]
    enabled: false
  video:
    kind: video
    extensions: [mp4, webm, mov]
    enabled: true
```

Đây là ví dụ một bộ cấu hình; file mặc định còn có `png` và `webp`.
Extension viết thường, không có dấu chấm và không trùng nhóm khác. Mỗi nhóm có `kind`
là `image` hoặc `video`; GIF dùng `image`. Có tối đa 25 nhóm để phù hợp dropdown Discord.
MIME do Discord trả về, nếu có, cũng phải phù hợp với `kind`.

- `enabled: false`: bot bỏ qua index mới cho định dạng đó, CLI bỏ qua file khi scan.
  Việc này không chặn người dùng gửi attachment trực tiếp lên Discord.
- Meme đã index vẫn được giữ lại và tìm kiếm bình thường khi tắt định dạng.
- `/meme search query:votay file_type:video` tìm fuzzy trong các extension thuộc `video`.
- `/meme list file_type:jpg` liệt kê cả JPG và JPEG. Có thể kết hợp `category`.
- Bỏ trống `file_type` để xem mọi định dạng đã index. Bộ lọc không làm thay đổi thuật toán
  tìm tiếng Việt có dấu/không dấu; phạm vi server và category luôn được giữ.

CLI dùng cùng policy khi chạy `python -m meme_manager.import_folder FOLDER --dry-run`
và upload thật. Dry-run đọc YAML và file local, không cần token hợp lệ, không kết nối
Discord và không mở/ghi SQLite.

Đổi `category_name` chỉ ảnh hưởng việc tìm/tạo nhóm khi không còn ID đã lưu.
Nhóm đã quản lý vẫn được nhận diện bằng ID; bot không tự đổi tên hay di chuyển kênh.
Các giới hạn cố định của Discord, cấu trúc schema và thứ tự ưu tiên thuật toán là ràng
buộc code; các giá trị vận hành được khai báo trong YAML. Thêm extension không bảo đảm
codec đó phát được trên mọi Discord client; bot không chuyển mã media.
