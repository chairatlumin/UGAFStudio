using UnrealBuildTool;

public class UGAFTelemetry : ModuleRules
{
    public UGAFTelemetry(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "HTTP", "Json" });
    }
}
