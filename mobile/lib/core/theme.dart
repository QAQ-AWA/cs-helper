import 'package:flutter/material.dart';

/// 与网页端 / 桌面端共用一套视觉语言：浅色底、白卡片、靛蓝强调色。
class AppColors {
  static const bg = Color(0xFFF5F6F8);
  static const surface = Color(0xFFFFFFFF);
  static const elevated = Color(0xFFF8FAFC);
  static const border = Color(0xFFE5E7EB);
  static const borderStrong = Color(0xFFD7DBE2);
  static const fg = Color(0xFF0F172A);
  static const fgSecondary = Color(0xFF475569);
  static const muted = Color(0xFF64748B);
  static const dim = Color(0xFF94A3B8);

  static const accent = Color(0xFF4F46E5);
  static const accentSoft = Color(0xFFEEF2FF);

  static const sideA = Color(0xFF2563EB);
  static const sideASoft = Color(0xFFEFF6FF);
  static const sideB = Color(0xFFEA580C);
  static const sideBSoft = Color(0xFFFFF7ED);

  static const ok = Color(0xFF16A34A);
  static const okSoft = Color(0xFFF0FDF4);
  static const warn = Color(0xFFB45309);
  static const warnSoft = Color(0xFFFFFBEB);
  static const bad = Color(0xFFDC2626);
  static const badSoft = Color(0xFFFEF2F2);
}

const appShadow = <BoxShadow>[
  BoxShadow(color: Color(0x0F0F172A), blurRadius: 3, offset: Offset(0, 1)),
];

BoxDecoration cardDecoration({Color? color, Color? borderColor}) {
  return BoxDecoration(
    color: color ?? AppColors.surface,
    borderRadius: BorderRadius.circular(12),
    border: Border.all(color: borderColor ?? AppColors.border),
    boxShadow: appShadow,
  );
}

InputDecoration fieldDecoration({
  String? hintText,
  Widget? suffixIcon,
  String? labelText,
}) {
  OutlineInputBorder border(Color color) => OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: BorderSide(color: color),
      );
  return InputDecoration(
    hintText: hintText,
    labelText: labelText,
    suffixIcon: suffixIcon,
    filled: true,
    fillColor: AppColors.elevated,
    hintStyle: const TextStyle(color: AppColors.dim, fontSize: 14),
    labelStyle: const TextStyle(color: AppColors.muted, fontSize: 13),
    contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
    border: border(AppColors.borderStrong),
    enabledBorder: border(AppColors.borderStrong),
    focusedBorder: border(AppColors.accent),
    errorBorder: border(AppColors.bad),
  );
}

ThemeData buildTheme() {
  final base = ThemeData(useMaterial3: true);
  final scheme = ColorScheme.fromSeed(seedColor: AppColors.accent).copyWith(
    primary: AppColors.accent,
    surface: AppColors.surface,
    error: AppColors.bad,
  );
  return base.copyWith(
    colorScheme: scheme,
    scaffoldBackgroundColor: AppColors.bg,
    dividerColor: AppColors.border,
    textTheme: base.textTheme.apply(
      bodyColor: AppColors.fg,
      displayColor: AppColors.fg,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.bg,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      foregroundColor: AppColors.fg,
      centerTitle: false,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.accent,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.fg,
        side: const BorderSide(color: AppColors.borderStrong),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: AppColors.accent,
        textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: AppColors.fg,
      contentTextStyle: const TextStyle(color: Colors.white, fontSize: 13),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: AppColors.accent),
    sliderTheme: const SliderThemeData(
      activeTrackColor: AppColors.accent,
      inactiveTrackColor: AppColors.border,
      thumbColor: AppColors.accent,
      overlayColor: Color(0x1A4F46E5),
      trackHeight: 3,
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
    ),
  );
}
