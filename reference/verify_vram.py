"""
SafeGuard VRAM Reality Check.
يحمّل نموذجاً صغيراً ويقيس استهلاك VRAM الفعلي vs النظري.
"""
import torch
import time

def vram_snapshot(label: str):
    """يطبع حالة الـ VRAM في هذه اللحظة."""
    allocated = torch.cuda.memory_allocated() / (1024 ** 3)
    reserved = torch.cuda.memory_reserved() / (1024 ** 3)
    total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    free = total - reserved
    print(f"\n--- {label} ---")
    print(f"  Allocated: {allocated:.2f} GB  (ما يستخدمه الكود فعلياً)")
    print(f"  Reserved:  {reserved:.2f} GB  (ما حجزه PyTorch من النظام)")
    print(f"  Free:      {free:.2f} GB  (المتاح للنماذج الأخرى)")
    print(f"  Total:     {total:.2f} GB")

def main():
    print("=" * 60)
    print("VRAM Reality Check")
    print("=" * 60)

    if not torch.cuda.is_available():
        print("[FAIL] CUDA غير متاح")
        return

    # نقطة الصفر — قبل أي شيء
    vram_snapshot("baseline (قبل تحميل أي نموذج)")

    # تحميل نموذج صغير من transformers للتأكد من سلاسة كل الـ stack
    # نستعمل distilbert (250MB) كـ canary — صغير، سريع، يثبت أن الـ pipeline يعمل
    print("\n[INFO] تحميل distilbert-base-uncased كاختبار canary...")
    from transformers import AutoModel, AutoTokenizer
    
    tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")
    model = AutoModel.from_pretrained("distilbert-base-uncased").to("cuda")
    model.eval()
    
    vram_snapshot("بعد تحميل distilbert على GPU")

    # forward pass حقيقي
    print("\n[INFO] تشغيل forward pass...")
    inputs = tokenizer("SafeGuard verification test", return_tensors="pt").to("cuda")
    with torch.no_grad():
        for _ in range(5):  # تكرار للوصول لاستقرار الـ caching
            _ = model(**inputs)
    torch.cuda.synchronize()
    
    vram_snapshot("بعد forward passes")

    # تنظيف
    del model, tokenizer, inputs
    torch.cuda.empty_cache()
    vram_snapshot("بعد empty_cache (نقطة العودة)")

    print("\n" + "=" * 60)
    print("✅ ML Pipeline يعمل من البداية للنهاية")
    print("=" * 60)

if __name__ == "__main__":
    main()